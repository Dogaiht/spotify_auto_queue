# Auto Queue — versão web

Interface visual para cadastrar regras "quando a música X tocar, adicione
a música Y na fila" e monitorar a reprodução do Spotify em segundo plano.

## Instalação

```
pip install -r requirements.txt
```

## Configuração

1. Crie um app em https://developer.spotify.com/dashboard
2. Em "Redirect URIs", adicione exatamente:
   ```
   http://127.0.0.1:8888/callback
   ```
3. Copie o Client ID e o Client Secret e preencha no início do arquivo
   `app.py` (variáveis `CLIENT_ID` e `CLIENT_SECRET`), ou defina as
   variáveis de ambiente `SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET`
   antes de rodar o servidor.

## Rodando

```
python app.py
```

Abra http://127.0.0.1:8888 no navegador. Clique em "Conectar ao Spotify",
autorize o app, e use a interface para:

- Buscar e escolher a música-gatilho e a música a enfileirar
- Salvar quantas regras quiser
- Remover regras (botão "×" em cada linha)
- Iniciar/parar o monitoramento em segundo plano com um clique

O monitoramento roda em uma thread dentro do próprio processo do Flask —
enquanto o servidor (`python app.py`) estiver rodando, ele continua
verificando a reprodução mesmo se você fechar a aba do navegador.

## Observações

- É necessário ter algum dispositivo Spotify ativo (app aberto tocando
  algo) para `add_to_queue` funcionar — é uma exigência da própria API do
  Spotify, não do código.
- As regras ficam salvas em `regras.json`, na mesma pasta.
- O token de acesso fica em `.cache`, também na mesma pasta — apague esse
  arquivo (ou use "Desconectar" na interface) para forçar novo login.
