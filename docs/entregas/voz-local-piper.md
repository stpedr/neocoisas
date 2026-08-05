# Entrega: Voz (TTS) local com Piper

> Melhoria de mídia — voz real **local**, sem depender de API paga.

## Resumo

Adiciona o **Piper** como provedor de voz: TTS **offline, local e gratuito**, com
voz **PT-BR**, mantendo a filosofia do projeto (custo zero, roda na máquina). Fica
como voz padrão, no lugar do placeholder silencioso; o ElevenLabs continua
disponível como opção.

## Motivação

O placeholder de voz gera só silêncio, e o ElevenLabs é pago/externo. O Piper dá
narração real e boa qualidade sem chave nem custo — coerente com o Ollama local.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `agents/media/providers.py` | `piper_voice()` — sintetiza com o binário `piper` e converte para mp3 (FFmpeg). |
| `agents/media/factory.py` | Provider `piper` no registro de voz. |
| `Dockerfile.api` | Instala `piper-tts` + `curl` e baixa a voz `pt_BR-faber-medium` para `/app/voices`. |
| `requirements-api.txt` | `piper-tts`. |
| `docker-compose.yml`, `.env(.example)` | `PIPER_MODEL` + `ANE_VOICE_PROVIDER=piper` como padrão. |
| `tests/test_media_factory.py` | Seleção do provider `piper`. |

## Como funciona

- `piper_voice(narração, dest)` roda `piper --model <PIPER_MODEL> --output_file
  tmp.wav` (texto via stdin) e converte o WAV para o `.mp3` esperado pelo pipeline.
- O modelo (`pt_BR-faber-medium.onnx`) é baixado na imagem Docker — **offline em
  runtime**. `PIPER_MODEL` aponta o caminho.
- Como o clipe usa `-shortest`, a duração do vídeo passa a acompanhar a narração real.
- Trocável pela aba ⚙️ Modelos: `placeholder | piper | elevenlabs`.

## Como validar

```bash
pytest -q tests/test_media_factory.py
# ao vivo (Docker): render de uma ideia com ANE_VOICE_PROVIDER=piper gera áudio real
curl -X POST http://localhost:8000/api/ideas/<ID>/render
```

## Critério de aceite

- [x] TTS local PT-BR, offline, sem chave.
- [x] Voz padrão do projeto (fallback placeholder; ElevenLabs opcional).
- [x] Empacotado na imagem Docker. 142 testes verdes.

## Pendências / próximos

- Outras vozes/idiomas do Piper (baixar mais modelos e expor na UI).
