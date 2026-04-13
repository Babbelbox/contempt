"""
tournament.py — Draai meerdere partijen over openingsposities, sla statistieken op.

Gebruik:
    python tournament.py
    python tournament.py --games 10 --nodes 300000
    python tournament.py --opening "Siciliaansch" --contempt-white 50 --games 4
"""
import argparse
import csv
import datetime
import re
from pathlib import Path
from typing import Callable

import chess
import chess.pgn

import config
from match import play_game, save_game


def load_openings(path: Path) -> list[dict]:
    """
    Laad openingsposities uit een EPD-bestand.
    EPD-formaat: <stuk> <kleur> <rokade> <en-passant> [opcodes]
    De eerste 4 velden vormen de FEN-basis; "0 1" wordt toegevoegd
    als halfzet-teller en volzetnummer zodat python-chess het accepteert.
    """
    openings = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tokens = line.split()
            if len(tokens) < 4:
                continue
            # Eerste 4 tokens = EPD-positie; voeg klokken toe voor geldige FEN
            fen = " ".join(tokens[:4]) + " 0 1"
            # Naam uit id "..." opcode
            m = re.search(r'\bid\s+"([^"]+)"', line)
            name = m.group(1) if m else "?"
            openings.append({"name": name, "fen": fen})
    return openings


def run_tournament(
    white_name: str,
    black_name: str,
    openings: list[dict],
    games_per_opening: int,
    white_move_limit: dict,
    black_move_limit: dict,
    white_overrides: dict,
    black_overrides: dict,
    pgn_path: Path,
    csv_path: Path,
    save_filter: str = "all",       # "all" | "white_wins" | "black_wins" | "decisive"
    progress_callback: Callable | None = None,
    stop_event=None,                # threading.Event — zet om te stoppen
) -> list[dict]:
    """
    Draait het tournament. Geeft lijst van resultaten terug.

    save_filter:
        "all"         → sla alle partijen op
        "white_wins"  → sla alleen 1-0 op
        "black_wins"  → sla alleen 0-1 op
        "decisive"    → sla 1-0 en 0-1 op (geen remises)

    progress_callback(done, total, info):
        Wordt aangeroepen na elke partij. info = {"opening", "white", "black", "result", "moves"}
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pgn_path.parent.mkdir(parents=True, exist_ok=True)

    results = []

    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["opening", "game_nr", "white", "black", "result", "moves",
                         "white_contempt", "black_contempt"])

        total = len(openings) * games_per_opening
        done  = 0

        for opening in openings:
            if stop_event and stop_event.is_set():
                break
            for i in range(games_per_opening):
                if stop_event and stop_event.is_set():
                    break
                if i % 2 == 0:
                    w, b = white_name, black_name
                    w_ov, b_ov = white_overrides, black_overrides
                    w_limit, b_limit = white_move_limit, black_move_limit
                else:
                    w, b = black_name, white_name
                    w_ov, b_ov = black_overrides, white_overrides
                    w_limit, b_limit = black_move_limit, white_move_limit

                done += 1
                print(f"[{done}/{total}] {opening['name']} | {w} vs {b}")

                try:
                    game = play_game(
                        white_name=w,
                        black_name=b,
                        fen=opening["fen"],
                        white_move_limit=w_limit,
                        black_move_limit=b_limit,
                        white_overrides=w_ov,
                        black_overrides=b_ov,
                    )
                    game.headers["Opening"] = opening["name"]
                    result = game.headers["Result"]
                    moves  = game.end().ply()
                    print(f"  -> {result} ({moves} halve zetten)")

                    # Filter: bepaal of deze partij opgeslagen wordt
                    should_save = (
                        save_filter == "all"
                        or (save_filter == "white_wins"  and result == "1-0")
                        or (save_filter == "black_wins"  and result == "0-1")
                        or (save_filter == "decisive"    and result in ("1-0", "0-1"))
                    )
                    if should_save:
                        save_game(game, pgn_path)

                    row = {
                        "opening": opening["name"],
                        "game_nr": i + 1,
                        "white": w,
                        "black": b,
                        "result": result,
                        "moves": moves,
                        "white_contempt": w_ov.get("Contempt", config.ENGINE_OPTIONS.get(w, {}).get("Contempt", "-")),
                        "black_contempt": b_ov.get("Contempt", config.ENGINE_OPTIONS.get(b, {}).get("Contempt", "-")),
                        "saved": should_save,
                    }
                    results.append(row)
                    writer.writerow([row[k] for k in
                                     ["opening", "game_nr", "white", "black", "result", "moves",
                                      "white_contempt", "black_contempt"]])
                    csvfile.flush()

                except Exception as exc:
                    print(f"  [fout] {exc}")
                    row = {"opening": opening["name"], "game_nr": i + 1, "white": w, "black": b,
                           "result": "ERROR", "moves": 0, "white_contempt": "-", "black_contempt": "-",
                           "saved": False}
                    results.append(row)
                    writer.writerow([row[k] for k in
                                     ["opening", "game_nr", "white", "black", "result", "moves",
                                      "white_contempt", "black_contempt"]])

                if progress_callback:
                    progress_callback(done, total, results[-1])

    print(f"\nKlaar. PGN: {pgn_path}\nCSV: {csv_path}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Tournament runner voor engine-vs-engine onderzoek")
    parser.add_argument("--white",           default="stockfish13", choices=list(config.ENGINE_PATHS))
    parser.add_argument("--black",           default="berserk",     choices=list(config.ENGINE_PATHS))
    parser.add_argument("--games",           type=int, default=2, help="Partijen per opening")
    parser.add_argument("--nodes",           type=int, default=None)
    parser.add_argument("--time",            type=float, default=None, help="Seconden per zet")
    parser.add_argument("--opening",         default=None, help="Filter op openingsnaam (gedeeltelijk)")
    parser.add_argument("--contempt-white",  type=int, default=None, help="Contempt voor wit (centipawns)")
    parser.add_argument("--contempt-black",  type=int, default=None, help="Contempt voor zwart")
    parser.add_argument("--save-filter",     default="all",
                        choices=["all", "white_wins", "black_wins", "decisive"],
                        help="Welke partijen opslaan in PGN")
    args = parser.parse_args()

    if args.nodes:
        move_limit = {"nodes": args.nodes}
    elif args.time:
        move_limit = {"time": args.time}
    else:
        move_limit = config.MOVE_LIMIT

    white_overrides = {}
    black_overrides = {}
    if args.contempt_white is not None:
        white_overrides["Contempt"] = args.contempt_white
    if args.contempt_black is not None:
        black_overrides["Contempt"] = args.contempt_black

    openings = load_openings(config.OPENINGS_FILE)
    if args.opening:
        openings = [o for o in openings if args.opening.lower() in o["name"].lower()]
        if not openings:
            print(f"Geen openingen gevonden met '{args.opening}'")
            return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{args.white}_vs_{args.black}_{timestamp}"
    pgn_path = config.GAMES_DIR   / f"{tag}.pgn"
    csv_path = config.RESULTS_DIR / f"{tag}.csv"

    run_tournament(
        white_name=args.white,
        black_name=args.black,
        openings=openings,
        games_per_opening=args.games,
        white_move_limit=move_limit,
        black_move_limit=move_limit,
        white_overrides=white_overrides,
        black_overrides=black_overrides,
        pgn_path=pgn_path,
        csv_path=csv_path,
        save_filter=args.save_filter,
    )


if __name__ == "__main__":
    main()
