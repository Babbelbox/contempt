"""
app.py — Streamlit GUI voor het schaakengine-onderzoeksproject.

Starten:
    streamlit run app.py
"""
import datetime
import io
import json
import queue
import threading
from pathlib import Path

import chess
import chess.pgn
import streamlit as st

import config
from tournament import run_tournament

# ---------------------------------------------------------------------------
# Standaardinstellingen — laden uit defaults.json, anders fabrieksinstellingen
# ---------------------------------------------------------------------------
_DEFAULTS_FILE = Path(__file__).parent / "defaults.json"

_FACTORY = {
    "wit_engine":      "stockfish18c",
    "zwart_engine":    "berserk",
    "kleur_modus":     "Wissel per partij",
    "contempt_wit":    config.CONTEMPT,
    "contempt_zwart":  0,
    "aantal_partijen": 2,
    "dt_wit":          "Nodes (reproduceerbaar)",
    "dt_zwart":        "Nodes (reproduceerbaar)",
    "nodes_wit":       500_000,
    "nodes_zwart":     500_000,
    "tijd_wit":        1.0,
    "tijd_zwart":      1.0,
    "filter_keuze":    "Alle partijen",
}

def _load_defaults() -> dict:
    if _DEFAULTS_FILE.exists():
        try:
            saved = json.loads(_DEFAULTS_FILE.read_text(encoding="utf-8"))
            return {**_FACTORY, **saved}   # gevonden waarden overschrijven fabriek
        except Exception:
            pass
    return _FACTORY.copy()

def _save_defaults(values: dict) -> None:
    _DEFAULTS_FILE.write_text(
        json.dumps(values, indent=2, ensure_ascii=False), encoding="utf-8"
    )

_D = _load_defaults()   # actieve standaarden voor deze sessie

# ---------------------------------------------------------------------------
# Pagina-configuratie
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Schaakengine Onderzoek",
    page_icon="♟",
    layout="wide",
)

st.title("♟ Schaakengine Onderzoek")
st.caption("Stockfish · Berserk · Contempt-analyse")

# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def pgn_to_fen(pgn_text: str) -> tuple[str | None, str | None]:
    """Parst PGN-tekst en geeft (FEN van eindpositie, foutmelding) terug."""
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text.strip()))
        if game is None:
            return None, "Geen geldige PGN gevonden."
        board = game.end().board()
        return board.fen(), None
    except Exception as exc:
        return None, str(exc)


def board_to_ascii(fen: str) -> str:
    """Geeft een eenvoudig ASCII-bordje terug."""
    board = chess.Board(fen)
    lines = []
    for rank in range(7, -1, -1):
        row = f"{rank + 1} "
        for file in range(8):
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            row += (piece.symbol() if piece else "·") + " "
        lines.append(row)
    lines.append("  a b c d e f g h")
    return "\n".join(lines)


def result_emoji(result: str) -> str:
    return {"1-0": "⬜ Wit wint", "0-1": "⬛ Zwart wint", "1/2-1/2": "🔲 Remise"}.get(result, result)


# ---------------------------------------------------------------------------
# Sessie-staat initialiseren
# ---------------------------------------------------------------------------
if "running"              not in st.session_state: st.session_state.running              = False
if "results"              not in st.session_state: st.session_state.results              = []
if "pgn_path"             not in st.session_state: st.session_state.pgn_path             = None
if "csv_path"             not in st.session_state: st.session_state.csv_path             = None
if "progress_q"           not in st.session_state: st.session_state.progress_q           = None
if "start_fen"            not in st.session_state: st.session_state.start_fen            = None
if "stop_event"           not in st.session_state: st.session_state.stop_event           = None
if "progress_done"        not in st.session_state: st.session_state.progress_done        = 0
if "progress_total"       not in st.session_state: st.session_state.progress_total       = 0
if "running_engines"      not in st.session_state: st.session_state.running_engines      = []
if "_last_error"          not in st.session_state: st.session_state._last_error          = None
# Widget-defaults — uit defaults.json of fabrieksinstellingen
if "nodes_wit"            not in st.session_state: st.session_state.nodes_wit            = _D["nodes_wit"]
if "nodes_zwart"          not in st.session_state: st.session_state.nodes_zwart          = _D["nodes_zwart"]
if "tijd_wit"             not in st.session_state: st.session_state.tijd_wit             = _D["tijd_wit"]
if "tijd_zwart"           not in st.session_state: st.session_state.tijd_zwart           = _D["tijd_zwart"]
if "dt_wit"               not in st.session_state: st.session_state.dt_wit               = _D["dt_wit"]
if "dt_zwart"             not in st.session_state: st.session_state.dt_zwart             = _D["dt_zwart"]
if "contempt_wit"         not in st.session_state: st.session_state.contempt_wit         = _D["contempt_wit"]
if "contempt_zwart"       not in st.session_state: st.session_state.contempt_zwart       = _D["contempt_zwart"]
if "aantal_partijen"      not in st.session_state: st.session_state.aantal_partijen      = _D["aantal_partijen"]
if "wit_engine"           not in st.session_state: st.session_state.wit_engine           = _D["wit_engine"]
if "zwart_engine"         not in st.session_state: st.session_state.zwart_engine         = _D["zwart_engine"]
if "kleur_modus"          not in st.session_state: st.session_state.kleur_modus          = _D["kleur_modus"]
if "filter_keuze"         not in st.session_state: st.session_state.filter_keuze         = _D["filter_keuze"]
if "gebruik_beginpositie" not in st.session_state: st.session_state.gebruik_beginpositie = False
if "invoer_methode"       not in st.session_state: st.session_state.invoer_methode       = "PGN"
if "pgn_tekst"            not in st.session_state: st.session_state.pgn_tekst            = ""
if "fen_invoer"           not in st.session_state: st.session_state.fen_invoer           = ""

# ---------------------------------------------------------------------------
# Voortgang-fragment — ververst elke seconde zonder volledige pagina-herlaad
# ---------------------------------------------------------------------------
@st.fragment(run_every=1.0)
def _voortgang_fragment():
    if not st.session_state.running:
        return
    q = st.session_state.progress_q
    if q is None:
        return

    # Drain queue non-blocking: verwerk alle nieuwe berichten in één tick
    while True:
        try:
            bericht = q.get_nowait()
        except queue.Empty:
            break

        if bericht is None:
            # Tournament klaar
            st.session_state.running = False
            st.rerun(scope="app")
            return

        if "__error__" in bericht:
            st.session_state.running = False
            st.session_state._last_error = bericht["__error__"]
            st.rerun(scope="app")
            return

        st.session_state.progress_done  = bericht["done"]
        st.session_state.progress_total = bericht["total"]
        st.session_state.results.append(bericht["info"])

    # Render voortgangsbalk
    done  = st.session_state.progress_done
    total = st.session_state.progress_total
    if total > 0:
        pct = done / total
        st.progress(pct, text=f"Partij {done}/{total} — {pct*100:.0f}%")
    else:
        st.info("⏳ Tournament loopt...")

    if st.session_state.results:
        last = st.session_state.results[-1]
        st.caption(f"{last['white']} vs {last['black']} — {result_emoji(last['result'])}")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_instellingen, tab_resultaten = st.tabs(
    ["⚙️ Instellingen", "📊 Resultaten"]
)

# ===========================================================================
# TAB 1 — Instellingen
# ===========================================================================
with tab_instellingen:
    engine_namen = list(config.ENGINE_PATHS.keys())

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Engines")
        wit_engine   = st.selectbox("Wit-engine",   engine_namen,
                                    index=engine_namen.index("stockfish18c") if "stockfish18c" in engine_namen else 0,
                                    key="wit_engine")
        zwart_engine = st.selectbox("Zwart-engine", engine_namen,
                                    index=engine_namen.index("berserk") if "berserk" in engine_namen else 1,
                                    key="zwart_engine")

        kleur_modus = st.radio(
            "Kleurverdeling",
            ["Wissel per partij", "Altijd wit-engine als wit", "Altijd zwart-engine als wit"],
            help="'Wissel' is aanbevolen: elke engine speelt evenveel met wit en zwart.",
            key="kleur_modus",
        )

    with col2:
        st.subheader("Contempt (centipawns)")
        contempt_wit   = st.slider("Contempt wit",   -100, 100,
                                   help="Positief = vermijdt remise. 0 = neutraal. 24 = SF13-standaard.",
                                   key="contempt_wit")
        contempt_zwart = st.slider("Contempt zwart", -100, 100,
                                   help="Alleen van toepassing als de engine Contempt ondersteunt.",
                                   key="contempt_zwart")

    st.divider()

    col3, col4, col5 = st.columns(3)
    with col3:
        st.subheader("Partijen")
        aantal_partijen = st.number_input("Aantal partijen (totaal)", min_value=1, max_value=200, key="aantal_partijen")
        st.caption("Tip: gebruik een even aantal voor symmetrische kleurverdeling.")

    NODE_OPTS = [50_000, 100_000, 200_000, 500_000, 750_000, 1_000_000, 1_500_000, 2_000_000]
    NODE_CAPS = {
        50_000:    "~0.05 sec – erg snel",
        100_000:   "~0.1 sec – snel",
        200_000:   "~0.2 sec – oriëntatie",
        500_000:   "~0.5 sec – standaard ✓",
        750_000:   "~0.75 sec – goed",
        1_000_000: "~1 sec – diep",
        1_500_000: "~1.5 sec – zeer diep",
        2_000_000: "~2 sec – maximum",
    }

    with col4:
        st.subheader(f"Denktijd {wit_engine}")
        methode_wit = st.radio("Methode", ["Nodes (reproduceerbaar)", "Seconden"], key="dt_wit")
        if methode_wit == "Nodes (reproduceerbaar)":
            n = st.select_slider("Nodes", NODE_OPTS,
                                 format_func=lambda x: f"{x:,}".replace(",", "."), key="nodes_wit")
            white_move_limit = {"nodes": n}
            st.caption(NODE_CAPS.get(n, ""))
        else:
            t = st.slider("Seconden per zet", 0.1, 10.0, step=0.1, key="tijd_wit")
            white_move_limit = {"time": t}

    with col5:
        st.subheader(f"Denktijd {zwart_engine}")
        methode_zwart = st.radio("Methode", ["Nodes (reproduceerbaar)", "Seconden"], key="dt_zwart")
        if methode_zwart == "Nodes (reproduceerbaar)":
            n = st.select_slider("Nodes", NODE_OPTS,
                                 format_func=lambda x: f"{x:,}".replace(",", "."), key="nodes_zwart")
            black_move_limit = {"nodes": n}
            st.caption(NODE_CAPS.get(n, ""))
        else:
            t = st.slider("Seconden per zet", 0.1, 10.0, step=0.1, key="tijd_zwart")
            black_move_limit = {"time": t}

    st.divider()

    st.subheader("Filter: welke partijen opslaan?")
    filter_keuze = st.radio(
        "Sla op in PGN-database:",
        ["Alle partijen", "Alleen winsten voor wit", "Alleen winsten voor zwart",
         "Alleen beslissende partijen (geen remises)"],
        horizontal=True,
        key="filter_keuze",
    )
    filter_map = {
        "Alle partijen":                            "all",
        "Alleen winsten voor wit":                  "white_wins",
        "Alleen winsten voor zwart":                "black_wins",
        "Alleen beslissende partijen (geen remises)": "decisive",
    }
    save_filter = filter_map[filter_keuze]

    st.divider()

    _save_col, _reset_col, _ = st.columns([2, 2, 4])
    with _save_col:
        if st.button("Sla op als standaard", use_container_width=True):
            _save_defaults({
                "wit_engine":      st.session_state.get("wit_engine",      _D["wit_engine"]),
                "zwart_engine":    st.session_state.get("zwart_engine",    _D["zwart_engine"]),
                "kleur_modus":     st.session_state.get("kleur_modus",     _D["kleur_modus"]),
                "contempt_wit":    st.session_state.get("contempt_wit",    _D["contempt_wit"]),
                "contempt_zwart":  st.session_state.get("contempt_zwart",  _D["contempt_zwart"]),
                "aantal_partijen": int(st.session_state.get("aantal_partijen", _D["aantal_partijen"])),
                "dt_wit":          st.session_state.get("dt_wit",          _D["dt_wit"]),
                "dt_zwart":        st.session_state.get("dt_zwart",        _D["dt_zwart"]),
                "nodes_wit":       st.session_state.get("nodes_wit",       _D["nodes_wit"]),
                "nodes_zwart":     st.session_state.get("nodes_zwart",     _D["nodes_zwart"]),
                "tijd_wit":        st.session_state.get("tijd_wit",        _D["tijd_wit"]),
                "tijd_zwart":      st.session_state.get("tijd_zwart",      _D["tijd_zwart"]),
                "filter_keuze":    st.session_state.get("filter_keuze",    _D["filter_keuze"]),
            })
            st.success("Standaardinstellingen opgeslagen.")
    with _reset_col:
        if st.button("Reset naar fabrieksinstellingen", use_container_width=True):
            if _DEFAULTS_FILE.exists():
                _DEFAULTS_FILE.unlink()
            for _k in _FACTORY:
                st.session_state[_k] = _FACTORY[_k]
            st.rerun()

    st.divider()

    st.subheader("Startpositie")

    gebruik_beginpositie = st.checkbox("Gebruik standaard beginpositie", value=False, key="gebruik_beginpositie")

    if not gebruik_beginpositie:
        invoer_methode = st.radio("Voer positie in via:", ["PGN", "FEN"], horizontal=True, key="invoer_methode")

        if invoer_methode == "PGN":
            pgn_tekst = st.text_area(
                "Plak hier een PGN-partij",
                height=200,
                placeholder="[Event \"...\"]\n[White \"...\"]\n...\n\n1.e4 e5 2.Nf3 ...",
                key="pgn_tekst",
            )
            if pgn_tekst.strip():
                fen, fout = pgn_to_fen(pgn_tekst)
                if fout:
                    st.error(f"PGN-fout: {fout}")
                else:
                    st.success(f"FEN: `{fen}`")
                    st.code(board_to_ascii(fen), language=None)
                    st.session_state.start_fen = fen
            else:
                st.session_state.start_fen = None

        else:  # FEN
            fen_invoer = st.text_input(
                "FEN",
                placeholder="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                key="fen_invoer",
            )
            if fen_invoer.strip():
                try:
                    chess.Board(fen_invoer)
                    st.success("Geldige FEN ✓")
                    st.code(board_to_ascii(fen_invoer), language=None)
                    st.session_state.start_fen = fen_invoer
                except Exception as e:
                    st.error(f"Ongeldige FEN: {e}")
                    st.session_state.start_fen = None
            else:
                st.session_state.start_fen = None
    else:
        st.session_state.start_fen = None
        st.info("Partijen starten vanuit de beginpositie.")

# ===========================================================================
# START-KNOP (buiten de tabs, altijd zichtbaar)
# ===========================================================================
st.divider()

start_col, stop_col, _ = st.columns([2, 1, 3])

with start_col:
    start_geklikt = st.button(
        "▶ Start partijen",
        type="primary",
        disabled=st.session_state.running,
        use_container_width=True,
    )
    _voortgang_fragment()  # rendert hier; ververst elke 1s zonder pagina-herlaad

with stop_col:
    stop_geklikt = st.button(
        "■ Stop",
        disabled=not st.session_state.running,
        use_container_width=True,
    )
    if stop_geklikt and st.session_state.stop_event:
        st.session_state.stop_event.set()
        st.session_state.running = False   # direct: UI reageert onmiddellijk
        st.rerun()                         # herlaad zodat Start-knop meteen actief wordt

# Foutmelding (buiten fragment zodat die zichtbaar blijft na herlaad)
if st.session_state._last_error:
    st.error(f"Tournament-fout:\n```\n{st.session_state._last_error}\n```")
    st.session_state._last_error = None

# ===========================================================================
# TAB 3 — Resultaten (tabel + downloads)
# Geen placeholders — direct renderen vanuit session_state.
# Streamlit vervangt de volledige output bij elke rerun, dus de tabel
# toont altijd de laatste resultaten zonder placeholder-toestand.
# ===========================================================================
with tab_resultaten:
    if st.session_state.results:
        st.dataframe(
            [{"Opening": r["opening"], "Wit": r["white"], "Zwart": r["black"],
              "Resultaat": result_emoji(r["result"]), "Zetten": r["moves"],
              "Opgeslagen": "✓" if r["saved"] else "—"} for r in st.session_state.results],
            use_container_width=True,
        )
    if not st.session_state.running:
        if st.session_state.pgn_path and Path(st.session_state.pgn_path).exists():
            st.download_button(
                "⬇ Download PGN",
                data=Path(st.session_state.pgn_path).read_bytes(),
                file_name=Path(st.session_state.pgn_path).name,
                mime="application/x-chess-pgn",
            )
        if st.session_state.csv_path and Path(st.session_state.csv_path).exists():
            st.download_button(
                "⬇ Download CSV",
                data=Path(st.session_state.csv_path).read_bytes(),
                file_name=Path(st.session_state.csv_path).name,
                mime="text/csv",
            )

# ===========================================================================
# TOURNAMENT STARTEN
# Lees alles uit session_state zodat de tab die actief is niet uitmaakt.
# ===========================================================================
if start_geklikt and not st.session_state.running:
    ss = st.session_state

    # --- Engines & kleur ---
    engine_namen_now = list(config.ENGINE_PATHS.keys())
    _wit   = ss.get("wit_engine",   engine_namen_now[0])
    _zwart = ss.get("zwart_engine", engine_namen_now[min(1, len(engine_namen_now)-1)])
    _kleur = ss.get("kleur_modus",  "Wissel per partij")
    wissel_kleuren = (_kleur == "Wissel per partij")
    if _kleur == "Altijd wit-engine als wit":
        wit, zw = _wit, _zwart
    elif _kleur == "Altijd zwart-engine als wit":
        wit, zw = _zwart, _wit
    else:
        wit, zw = _wit, _zwart

    # --- Denktijd ---
    if ss.get("dt_wit", "Nodes (reproduceerbaar)") == "Nodes (reproduceerbaar)":
        white_move_limit = {"nodes": ss.get("nodes_wit", 500_000)}
    else:
        white_move_limit = {"time": ss.get("tijd_wit", 1.0)}

    if ss.get("dt_zwart", "Nodes (reproduceerbaar)") == "Nodes (reproduceerbaar)":
        black_move_limit = {"nodes": ss.get("nodes_zwart", 500_000)}
    else:
        black_move_limit = {"time": ss.get("tijd_zwart", 1.0)}

    # --- Contempt & filter ---
    white_overrides = {"Contempt": ss.get("contempt_wit",   config.CONTEMPT)}
    black_overrides = {"Contempt": ss.get("contempt_zwart", 0)}
    filter_map = {
        "Alle partijen":                              "all",
        "Alleen winsten voor wit":                    "white_wins",
        "Alleen winsten voor zwart":                  "black_wins",
        "Alleen beslissende partijen (geen remises)": "decisive",
    }
    save_filter = filter_map.get(ss.get("filter_keuze", "Alle partijen"), "all")
    aantal_partijen = int(ss.get("aantal_partijen", 2))

    # --- Opening: altijd dezelfde startpositie voor alle partijen ---
    if ss.start_fen:
        openings = [{"name": "Aangepaste positie", "fen": ss.start_fen}]
    else:
        openings = [{"name": "Beginpositie", "fen": chess.Board().fen()}]
    games_per_opening = aantal_partijen

    # --- State ---
    ss.running          = True
    ss.results          = []
    ss.stop_event       = threading.Event()
    ss.progress_done    = 0
    ss.progress_total   = len(openings) * games_per_opening  # direct zetten zodat % meteen klopt
    ss.running_engines  = [wit, zw]
    q = queue.Queue()
    ss.progress_q = q

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{wit}_vs_{zw}_{timestamp}"
    pgn_path = config.GAMES_DIR   / f"{tag}.pgn"
    csv_path = config.RESULTS_DIR / f"{tag}.csv"
    ss.pgn_path = str(pgn_path)
    ss.csv_path = str(csv_path)

    def callback(done, total, info):
        q.put({"done": done, "total": total, "info": info})

    stop_event = ss.stop_event

    def achtergrond():
        # Op Windows gebruikt Streamlit/Tornado een SelectorEventLoop die geen
        # subprocessen ondersteunt. chess.engine.popen_uci() heeft ProactorEventLoop nodig.
        import asyncio as _aio, sys
        if sys.platform == "win32":
            _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())
        try:
            run_tournament(
                white_name=wit,
                black_name=zw,
                openings=openings,
                games_per_opening=games_per_opening,
                white_move_limit=white_move_limit,
                black_move_limit=black_move_limit,
                white_overrides=white_overrides,
                black_overrides=black_overrides,
                pgn_path=pgn_path,
                csv_path=csv_path,
                save_filter=save_filter,
                progress_callback=callback,
                stop_event=stop_event,
                wissel_kleuren=wissel_kleuren,
            )
        except Exception:
            import traceback
            q.put({"__error__": traceback.format_exc()})
        finally:
            q.put(None)  # signaal: klaar

    threading.Thread(target=achtergrond, daemon=True).start()
    st.rerun()

