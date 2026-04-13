"""
match.py — Speel één partij tussen twee UCI-engines.

Gebruik:
    python match.py
    python match.py --white stockfish --black berserk --fen "<FEN>" --games 2
    python match.py --white stockfish --black berserk --nodes 1000000
"""
import argparse
import datetime
import chess
import chess.engine
import chess.pgn
from pathlib import Path

import config


def apply_options(engine: chess.engine.SimpleEngine, name: str, overrides: dict) -> None:
    """Pas UCI-opties toe; sla opties over die de engine niet kent."""
    base = dict(config.ENGINE_OPTIONS.get(name, {}))
    base.update(overrides)
    supported = engine.options
    for key, value in base.items():
        if key in supported:
            engine.configure({key: value})
        else:
            print(f"  [info] {name}: UCI-optie '{key}' niet ondersteund, overgeslagen")


def _make_limit(cfg: dict) -> chess.engine.Limit:
    if "nodes" in cfg:
        return chess.engine.Limit(nodes=cfg["nodes"])
    return chess.engine.Limit(time=cfg["time"])


def play_game(
    white_name: str,
    black_name: str,
    fen: str | None = None,
    white_move_limit: dict | None = None,
    black_move_limit: dict | None = None,
    white_overrides: dict | None = None,
    black_overrides: dict | None = None,
) -> chess.pgn.Game:
    """
    Speel één partij. Geeft een chess.pgn.Game terug.

    Args:
        white_name:        Sleutel in config.ENGINE_PATHS voor het witte stuk.
        black_name:        Sleutel voor zwart.
        fen:               Startpositie als FEN-string (None = beginpositie).
        white_move_limit:  Dict met 'nodes' of 'time' voor wit; overschrijft config.MOVE_LIMIT.
        black_move_limit:  Dict met 'nodes' of 'time' voor zwart; overschrijft config.MOVE_LIMIT.
        white_overrides:   Extra UCI-opties voor wit (bijv. {"Contempt": 50}).
        black_overrides:   Extra UCI-opties voor zwart.
    """
    white_limit = _make_limit(white_move_limit or config.MOVE_LIMIT)
    black_limit = _make_limit(black_move_limit or config.MOVE_LIMIT)

    white_path = config.ENGINE_PATHS[white_name]
    black_path = config.ENGINE_PATHS[black_name]

    board = chess.Board(fen) if fen else chess.Board()
    game  = chess.pgn.Game()
    game.setup(board)

    # PGN-headers
    game.headers["White"]  = white_name
    game.headers["Black"]  = black_name
    game.headers["Date"]   = datetime.date.today().isoformat()
    game.headers["FEN"]    = board.fen()
    if fen:
        game.headers["SetUp"] = "1"

    RESIGN_CP = 300  # geef op bij +3 of meer voor één kant

    with (
        chess.engine.SimpleEngine.popen_uci(str(white_path)) as white_engine,
        chess.engine.SimpleEngine.popen_uci(str(black_path)) as black_engine,
    ):
        apply_options(white_engine, white_name, white_overrides or {})
        apply_options(black_engine, black_name, black_overrides or {})

        node = game
        resign_result = None

        while not board.is_game_over(claim_draw=True):
            engine = white_engine if board.turn == chess.WHITE else black_engine
            limit  = white_limit   if board.turn == chess.WHITE else black_limit
            play_result = engine.play(board, limit, info=chess.engine.INFO_SCORE)
            board.push(play_result.move)
            node = node.add_variation(play_result.move)

            # Opgave-check: als evaluatie >= +3 geeft de verliezende kant op
            score = play_result.info.get("score")
            if score is not None:
                cp = score.white().score()  # None bij mat, anders centipawns
                if cp is not None:
                    if cp >= RESIGN_CP:
                        node.comment = f"Zwart geeft op (eval: +{cp/100:.1f})"
                        resign_result = "1-0"
                        break
                    elif cp <= -RESIGN_CP:
                        node.comment = f"Wit geeft op (eval: {cp/100:.1f})"
                        resign_result = "0-1"
                        break

        game.headers["Result"] = resign_result or board.result(claim_draw=True)

    return game


def save_game(game: chess.pgn.Game, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        print(game, file=f)
        print(file=f)


def main():
    parser = argparse.ArgumentParser(description="Speel één of meer partijen tussen twee engines")
    parser.add_argument("--white",  default="stockfish", choices=list(config.ENGINE_PATHS))
    parser.add_argument("--black",  default="berserk",   choices=list(config.ENGINE_PATHS))
    parser.add_argument("--fen",    default=None,        help="Startpositie als FEN-string")
    parser.add_argument("--games",  type=int, default=2, help="Aantal partijen (kleuren worden gewisseld)")
    parser.add_argument("--nodes",  type=int, default=None, help="Nodes per zet (overschrijft config)")
    parser.add_argument("--output", default=None,        help="Pad voor PGN-uitvoer")
    args = parser.parse_args()

    move_limit = {"nodes": args.nodes} if args.nodes else None

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output = Path(args.output) if args.output else (
        config.GAMES_DIR / f"{args.white}_vs_{args.black}_{timestamp}.pgn"
    )

    for i in range(args.games):
        # Wissel kleuren elke partij
        white = args.white if i % 2 == 0 else args.black
        black = args.black if i % 2 == 0 else args.white

        print(f"Partij {i+1}/{args.games}: {white} (wit) vs {black} (zwart)")
        game = play_game(white, black, fen=args.fen,
                         white_move_limit=move_limit, black_move_limit=move_limit)
        result = game.headers["Result"]
        moves  = game.end().ply()
        print(f"  Resultaat: {result} na {moves} halve zetten")

        save_game(game, output)

    print(f"\nPGN opgeslagen: {output}")


if __name__ == "__main__":
    main()
