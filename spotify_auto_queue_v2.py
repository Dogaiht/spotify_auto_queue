
import json
import os
import threading
import time

import spotipy
from spotipy.oauth2 import SpotifyOAuth

# ==========================================================================
# CONFIGURAÇÕES — edite aqui
# ==========================================================================

CLIENT_ID = "SEU_CLIENT_ID_AQUI"
CLIENT_SECRET = "SEU_CLIENT_SECRET_AQUI"
REDIRECT_URI = "http://127.0.0.1:8888/callback"

SCOPE = "user-read-currently-playing user-read-playback-state user-modify-playback-state"

ARQUIVO_REGRAS = "regras.json"
POLL_INTERVAL = 3  # segundos entre cada verificação

# ==========================================================================


class GerenciadorDeRegras:
    """Carrega, salva, adiciona e remove as regras de gatilho -> fila."""

    def __init__(self, caminho: str):
        self.caminho = caminho
        self.regras = self._carregar()
        self.lock = threading.Lock()

    def _carregar(self):
        if os.path.exists(self.caminho):
            with open(self.caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def salvar(self):
        with open(self.caminho, "w", encoding="utf-8") as f:
            json.dump(self.regras, f, ensure_ascii=False, indent=2)

    def adicionar(self, gatilho: dict, enfileirar: dict):
        with self.lock:
            self.regras.append(
                {
                    "gatilho_uri": gatilho["uri"],
                    "gatilho_nome": f'{gatilho["name"]} - {gatilho["artist"]}',
                    "fila_uri": enfileirar["uri"],
                    "fila_nome": f'{enfileirar["name"]} - {enfileirar["artist"]}',
                    "ja_enfileirada": False,
                }
            )
            self.salvar()

    def remover(self, indice: int) -> bool:
        with self.lock:
            if 0 <= indice < len(self.regras):
                self.regras.pop(indice)
                self.salvar()
                return True
            return False

    def listar(self):
        with self.lock:
            return list(self.regras)


def buscar_musica(sp: spotipy.Spotify, termo: str):
    """Busca músicas no Spotify pelo nome e devolve até 5 candidatas."""
    resultado = sp.search(q=termo, type="track", limit=5)
    itens = resultado["tracks"]["items"]
    candidatas = []
    for item in itens:
        candidatas.append(
            {
                "uri": item["uri"],
                "name": item["name"],
                "artist": ", ".join(a["name"] for a in item["artists"]),
            }
        )
    return candidatas


def escolher_musica(sp: spotipy.Spotify, rotulo: str):
    """Pede um termo de busca ao usuário e deixa ele escolher entre os resultados."""
    termo = input(f"Digite o nome (ou artista + nome) d{rotulo}: ").strip()
    if not termo:
        print("Busca vazia, cancelado.")
        return None

    candidatas = buscar_musica(sp, termo)
    if not candidatas:
        print("Nenhuma música encontrada.")
        return None

    print(f"\nResultados para '{termo}':")
    for i, c in enumerate(candidatas):
        print(f"  [{i}] {c['name']} - {c['artist']}")

    escolha = input("Escolha o número (ou Enter para cancelar): ").strip()
    if not escolha:
        return None
    try:
        idx = int(escolha)
        return candidatas[idx]
    except (ValueError, IndexError):
        print("Escolha inválida.")
        return None


class Monitor:
    """Roda em uma thread separada verificando a reprodução atual."""

    def __init__(self, sp: spotipy.Spotify, gerenciador: GerenciadorDeRegras):
        self.sp = sp
        self.gerenciador = gerenciador
        self._thread = None
        self._parar = threading.Event()

    def rodando(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def iniciar(self):
        if self.rodando():
            print("O monitoramento já está em execução.")
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("Monitoramento iniciado em segundo plano.")

    def parar(self):
        if not self.rodando():
            print("O monitoramento não está em execução.")
            return
        self._parar.set()
        self._thread.join(timeout=POLL_INTERVAL + 2)
        print("Monitoramento parado.")

    def _loop(self):
        while not self._parar.is_set():
            try:
                atual = self.sp.current_playback()
                uri_atual = None
                if atual and atual.get("item"):
                    uri_atual = atual["item"]["uri"]

                regras = self.gerenciador.listar()
                for i, regra in enumerate(regras):
                    if uri_atual == regra["gatilho_uri"]:
                        if not regra["ja_enfileirada"]:
                            self.sp.add_to_queue(regra["fila_uri"])
                            print(
                                f"\n[{time.strftime('%H:%M:%S')}] Detectada "
                                f"'{regra['gatilho_nome']}' — adicionando "
                                f"'{regra['fila_nome']}' à fila!"
                            )
                            with self.gerenciador.lock:
                                self.gerenciador.regras[i]["ja_enfileirada"] = True
                                self.gerenciador.salvar()
                    else:
                        if regra["ja_enfileirada"]:
                            with self.gerenciador.lock:
                                self.gerenciador.regras[i]["ja_enfileirada"] = False
                                self.gerenciador.salvar()

            except Exception as erro:
                print(f"\n[Monitor] Erro durante verificação: {erro}")

            self._parar.wait(POLL_INTERVAL)


def imprimir_menu():
    print(
        "\n===== Spotify Auto Queue =====\n"
        "1. Adicionar regra (música-gatilho -> música a enfileirar)\n"
        "2. Remover regra\n"
        "3. Listar regras\n"
        "4. Iniciar monitoramento em segundo plano\n"
        "5. Parar monitoramento\n"
        "6. Sair\n"
        "==============================="
    )


def main():
    sp = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=SCOPE,
        )
    )

    gerenciador = GerenciadorDeRegras(ARQUIVO_REGRAS)
    monitor = Monitor(sp, gerenciador)

    print("Conectado ao Spotify com sucesso.")

    while True:
        imprimir_menu()
        opcao = input("Escolha uma opção: ").strip()

        if opcao == "1":
            gatilho = escolher_musica(sp, "a música GATILHO")
            if not gatilho:
                continue
            enfileirar = escolher_musica(sp, "a música a ENFILEIRAR")
            if not enfileirar:
                continue
            gerenciador.adicionar(gatilho, enfileirar)
            print(
                f"Regra salva: quando tocar '{gatilho['name']} - {gatilho['artist']}', "
                f"enfileirar '{enfileirar['name']} - {enfileirar['artist']}'."
            )

        elif opcao == "2":
            regras = gerenciador.listar()
            if not regras:
                print("Não há regras cadastradas.")
                continue
            for i, r in enumerate(regras):
                print(f"  [{i}] {r['gatilho_nome']} -> {r['fila_nome']}")
            escolha = input("Número da regra a remover (Enter para cancelar): ").strip()
            if not escolha:
                continue
            try:
                idx = int(escolha)
                if gerenciador.remover(idx):
                    print("Regra removida.")
                else:
                    print("Índice inválido.")
            except ValueError:
                print("Entrada inválida.")

        elif opcao == "3":
            regras = gerenciador.listar()
            if not regras:
                print("Não há regras cadastradas.")
            else:
                for i, r in enumerate(regras):
                    status = "ativa" if not monitor.rodando() else (
                        "aguardando" if not r["ja_enfileirada"] else "já disparada nesta reprodução"
                    )
                    print(f"  [{i}] {r['gatilho_nome']} -> {r['fila_nome']}  ({status})")

        elif opcao == "4":
            monitor.iniciar()

        elif opcao == "5":
            monitor.parar()

        elif opcao == "6":
            if monitor.rodando():
                monitor.parar()
            print("Até mais!")
            break

        else:
            print("Opção inválida.")


if __name__ == "__main__":
    main()
