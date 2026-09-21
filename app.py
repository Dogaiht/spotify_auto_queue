"""
Spotify Auto Queue - versão web

Servidor Flask que expõe uma interface visual para cadastrar regras
"quando a música X tocar, adicione a música Y na fila" e monitora a
reprodução do Spotify em segundo plano (thread própria) para executá-las.

--------------------------------------------------------------------------
COMO USAR
--------------------------------------------------------------------------
1. Instale as dependências:
       pip install -r requirements.txt

2. Crie um app em https://developer.spotify.com/dashboard
   - Redirect URI: http://127.0.0.1:8888/callback

3. Preencha CLIENT_ID e CLIENT_SECRET abaixo (ou defina como variáveis de
   ambiente SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET).

4. Rode:
       python app.py

5. Abra http://127.0.0.1:8888 no navegador, clique em "Conectar ao
   Spotify", autorize o app e use a interface para cadastrar regras e
   iniciar o monitoramento.
--------------------------------------------------------------------------
"""

import json
import os
import threading
import time

from flask import Flask, jsonify, redirect, render_template, request
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# ==========================================================================
# CONFIGURAÇÕES — edite aqui (ou use variáveis de ambiente)
# ==========================================================================

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "SEU_CLIENT_ID_AQUI")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "SEU_CLIENT_SECRET_AQUI")
REDIRECT_URI = "http://127.0.0.1:8888/callback"

SCOPE = "user-read-currently-playing user-read-playback-state user-modify-playback-state"

ARQUIVO_REGRAS = os.path.join(os.path.dirname(__file__), "regras.json")
CACHE_PATH = os.path.join(os.path.dirname(__file__), ".cache")
POLL_INTERVAL = 3  # segundos entre cada verificação de reprodução

# ==========================================================================

app = Flask(__name__)

auth_manager = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE,
    cache_path=CACHE_PATH,
    open_browser=False,
)

spotify_client = None  # criado após login, ver get_spotify()


def get_spotify():
    """Devolve um cliente Spotify autenticado, ou None se não houver login."""
    global spotify_client
    token_info = auth_manager.get_cached_token()
    if not token_info:
        return None
    if spotify_client is None:
        spotify_client = spotipy.Spotify(auth_manager=auth_manager)
    return spotify_client


# --------------------------------------------------------------------------
# Regras (persistidas em regras.json)
# --------------------------------------------------------------------------

regras_lock = threading.Lock()


def carregar_regras():
    if os.path.exists(ARQUIVO_REGRAS):
        with open(ARQUIVO_REGRAS, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def salvar_regras(regras):
    with open(ARQUIVO_REGRAS, "w", encoding="utf-8") as f:
        json.dump(regras, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Monitor em segundo plano
# --------------------------------------------------------------------------

class Monitor:
    def __init__(self):
        self._thread = None
        self._parar = threading.Event()
        self.now_playing = None

    def rodando(self):
        return self._thread is not None and self._thread.is_alive()

    def iniciar(self):
        if self.rodando():
            return False
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def parar(self):
        if not self.rodando():
            return False
        self._parar.set()
        self._thread.join(timeout=POLL_INTERVAL + 2)
        return True

    def _loop(self):
        while not self._parar.is_set():
            sp = get_spotify()
            if sp is None:
                self._parar.wait(POLL_INTERVAL)
                continue
            try:
                atual = sp.current_playback()
                uri_atual = None
                if atual and atual.get("item"):
                    item = atual["item"]
                    uri_atual = item["uri"]
                    imagens = item["album"]["images"]
                    self.now_playing = {
                        "uri": uri_atual,
                        "name": item["name"],
                        "artist": ", ".join(a["name"] for a in item["artists"]),
                        "image": imagens[-1]["url"] if imagens else None,
                        "is_playing": atual.get("is_playing", False),
                    }
                else:
                    self.now_playing = None

                with regras_lock:
                    regras = carregar_regras()
                    alterado = False
                    for regra in regras:
                        if uri_atual == regra["gatilho_uri"]:
                            if not regra.get("ja_enfileirada"):
                                sp.add_to_queue(regra["fila_uri"])
                                regra["ja_enfileirada"] = True
                                regra["disparada_em"] = time.time()
                                alterado = True
                        else:
                            if regra.get("ja_enfileirada"):
                                regra["ja_enfileirada"] = False
                                alterado = True
                    if alterado:
                        salvar_regras(regras)

            except Exception as erro:
                print(f"[Monitor] erro: {erro}")

            self._parar.wait(POLL_INTERVAL)


monitor = Monitor()

# --------------------------------------------------------------------------
# Rotas — páginas
# --------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login():
    return redirect(auth_manager.get_authorize_url())


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if code:
        auth_manager.get_access_token(code, as_dict=False)
    return redirect("/")


@app.route("/logout")
def logout():
    global spotify_client
    if os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)
    spotify_client = None
    if monitor.rodando():
        monitor.parar()
    return redirect("/")


# --------------------------------------------------------------------------
# Rotas — API
# --------------------------------------------------------------------------


@app.route("/api/state")
def api_state():
    sp = get_spotify()
    with regras_lock:
        regras = carregar_regras()
    return jsonify(
        {
            "authenticated": sp is not None,
            "monitor_running": monitor.rodando(),
            "now_playing": monitor.now_playing,
            "rules": regras,
        }
    )


@app.route("/api/search")
def api_search():
    sp = get_spotify()
    if sp is None:
        return jsonify({"error": "not_authenticated"}), 401

    termo = request.args.get("q", "").strip()
    if not termo:
        return jsonify([])

    resultado = sp.search(q=termo, type="track", limit=6)
    itens = resultado["tracks"]["items"]
    candidatas = []
    for item in itens:
        imagens = item["album"]["images"]
        candidatas.append(
            {
                "uri": item["uri"],
                "name": item["name"],
                "artist": ", ".join(a["name"] for a in item["artists"]),
                "image": imagens[-1]["url"] if imagens else None,
            }
        )
    return jsonify(candidatas)


@app.route("/api/rules", methods=["POST"])
def api_add_rule():
    dados = request.get_json(force=True)
    gatilho = dados.get("gatilho")
    fila = dados.get("fila")
    if not gatilho or not fila:
        return jsonify({"error": "dados incompletos"}), 400

    nova_regra = {
        "gatilho_uri": gatilho["uri"],
        "gatilho_nome": gatilho["name"],
        "gatilho_artista": gatilho["artist"],
        "gatilho_imagem": gatilho.get("image"),
        "fila_uri": fila["uri"],
        "fila_nome": fila["name"],
        "fila_artista": fila["artist"],
        "fila_imagem": fila.get("image"),
        "ja_enfileirada": False,
    }

    with regras_lock:
        regras = carregar_regras()
        regras.append(nova_regra)
        salvar_regras(regras)

    return jsonify(nova_regra), 201


@app.route("/api/rules/<int:indice>", methods=["DELETE"])
def api_remove_rule(indice):
    with regras_lock:
        regras = carregar_regras()
        if 0 <= indice < len(regras):
            regras.pop(indice)
            salvar_regras(regras)
            return jsonify({"ok": True})
    return jsonify({"error": "índice inválido"}), 404


@app.route("/api/monitor/start", methods=["POST"])
def api_monitor_start():
    if get_spotify() is None:
        return jsonify({"error": "not_authenticated"}), 401
    monitor.iniciar()
    return jsonify({"monitor_running": True})


@app.route("/api/monitor/stop", methods=["POST"])
def api_monitor_stop():
    monitor.parar()
    return jsonify({"monitor_running": False})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8888, debug=False)
