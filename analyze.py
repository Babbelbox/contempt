"""
analyze.py — Annoteer een PGN-bestand met engine-evaluaties.

Gebruik:
    python analyze.py games/mijn_partij.pgn
    python analyze.py games/mijn_partij.pgn --engine stockfish --depth 20
    python analyze.py games/mijn_partij.pgn --compare  # beide engines naast elkaar
"""
import argparse
import sys
from pathlib import Path

import chess
import chess.engine
import chess.pgn

import config


def evaluate_game(
    game: chess.pgn.Game,
    engine: chess.engine.SimpleEngine,
    engine_name: str,
    depth: int,
    comment_prefix: str = "",
) -> chess.pgn.Game:
    """Voeg centipawn-evaluaties toe als PGN-commentaar."""
    board = game.board()
    node  = game

    for move in game.mainline_moves():
        board.push(move)
        node = node.variations[0] if node.variations else node

        info = engine.analyse(board, chess.engine.Limit(depth=depth))
        score = info["score"].white()

        if score.is_mate():
            comment = f"{comment_prefix}M{score.mate()}"
        else:
            cp = score.score()
            comment = f"{comment_prefix}{cp:+d}cp"

        existing = node.comment or ""
        node.comment = (existing + " " + comment).strip()

    return game


def compare_games(
    game: chess.pgn.Game,
    engines: dict[str, chess.engine.SimpleEngine],
    depth: int,
) -> None:
    """Print een tabel met evaluaties van beide engines per zet."""
    board  = game.board()
    names  = list(engines.keys())
    header = f"{'Zet':<6} {'Zet':<8}" + "".join(f"{n:>12}" for n in names)
    print(header)
    print("-" * len(header))

    move_nr = 1
    for move in game.mainline_moves():
        san = board.san(move)
        board.push(move)

        scores = []
        for eng in engines.values():
            info  = eng.analyse(board, chess.engine.Limit(depth=depth))
            score = info["score"].white()
            if score.is_mate():
                scores.append(f"M{score.mate()}")
            else:
                scores.append(f"{score.score():+d}")

        color = "w" if board.turn == chess.BLACK else "b"
        label = f"{move_nr}{color}."
        row   = f"{label:<6} {san:<8}" + "".join(f"{s:>12}" for s in scores)
        print(row)

        if board.turn == chess.WHITE:
            move_nr += 1


def main():
    parser = argparse.ArgumentParser(description="Annoteer PGN met engine-evaluaties")
    parser.add_argument("pgn", help="Pad naar PGN-bestand")
    parser.add_argument("--engine",  default="stockfish", choices=list(config.ENGINE_PATHS),
                        help="Engine voor annotaties")
    parser.add_argument("--depth",   type=int, default=18, help="Zoekdiepte")
    parser.add_argument("--compare", action="store_true",
                        help="Vergelijk beide engines naast elkaar (print tabel)")
    parser.add_argument("--game",    type=int, default=1,
                        help="Welke partij uit het PGN-bestand (1-gebaseerd)")
    args = parser.parse_args()

    pgn_path = Path(args.pgn)
    if not pgn_path.exists():
        print(f"Bestand niet gevonden: {pgn_path}")
        sys.exit(1)

    with open(pgn_path, encoding="utf-8") as f:
        game = None
        for _ in range(args.game):
            game = chess.pgn.read_game(f)
        if game is None:
            print(f"Partij {args.game} niet gevonden in {pgn_path}")
            sys.exit(1)

    print(f"Partij: {game.headers.get('White')} vs {game.headers.get('Black')} "
          f"({game.headers.get('Result', '?')})")
    print(f"Opening: {game.headers.get('Opening', game.headers.get('FEN', 'beginpositie'))}\n")

    if args.compare:
        with (
            chess.engine.SimpleEngine.popen_uci(str(config.ENGINE_PATHS["stockfish"])) as sf,
            chess.engine.SimpleEngine.popen_uci(str(config.ENGINE_PATHS["berserk"]))   as bk,
        ):
            compare_games(game, {"Stockfish": sf, "Berserk": bk}, depth=args.depth)
    else:
        engine_path = config.ENGINE_PATHS[args.engine]
        output_path = pgn_path.with_stem(pgn_path.stem + f"_annotated_{args.engine}")

        with chess.engine.SimpleEngine.popen_uci(str(engine_path)) as eng:
            annotated = evaluate_game(game, eng, args.engine, depth=args.depth)

        with open(output_path, "w", encoding="utf-8") as f:
            print(annotated, file=f)

        print(f"Geannoteerde PGN opgeslagen: {output_path}")


if __name__ == "__main__":
    main()
