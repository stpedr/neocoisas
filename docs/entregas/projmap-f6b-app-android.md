# ProjMap F6b — App Android (APK)

## Resumo
App Android (Capacitor 7) que pareia com o mestre por QR ou IP + token, lembra
o último mestre e abre o remote do celular (F6a) dentro do app. APK de debug
gerado e validado no emulador.

## Motivação
O PLANO pede um "APK de debug que instala e controla o mestre". Com o app, o
operador não precisa digitar endereço no navegador nem perder a aba, e o app
reconecta sozinho ao abrir.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `projmap/android/` | Novo projeto Capacitor: `package.json`, `capacitor.config.json`, lançador (`www/`), projeto nativo `android/` |
| `projmap/android/www/launcher.js` | Pareamento (QR com jsQR ou digitado), validação de IP privado, teste de alcance, recentes e reconexão automática |
| `android/app/src/main/AndroidManifest.xml` · `res/xml/network_security_config.xml` | Cleartext na LAN e permissão `CAMERA` |
| `projmap/android/tests/launcher.test.cjs` | 5 testes (IP privado, parse do QR, URL) |
| `projmap/ui/app/remote/page.tsx` | Botão **Trocar mestre** quando aberto no app (user agent `ProjMapApp`) |
| `projmap/ui/app/layout.tsx` · `globals.css` | `viewport-fit=cover` e safe-area no topo (Android 15 edge-to-edge) |
| `.github/workflows/ci.yml` | Roda os testes do lançador |
| `projmap/android/README.md` · `projmap/README.md` · `board/seed.py` | Docs e cards |

## Como funciona
1. O app abre no lançador (`https://localhost/`, origem do Capacitor).
2. QR: a câmera tira uma foto, o jsQR decodifica no aparelho e o lançador lê
   `http://<ip>:<porta>/remote/#t=<token>`. Também dá para digitar IP e token.
3. O lançador só aceita IPs privados, testa se o mestre responde (`/remote/` é
   estático e público), salva em "recentes" e navega a WebView para o remote.
4. O `allowNavigation` mantém dentro do app só os hosts da LAN. O padrão casa
   segmento por segmento, por isso `192.168.*.*` e não `192.168.*`; esse bug
   apareceu no teste no emulador.
5. No remote, **Trocar mestre** volta para `https://localhost/?pick=1`, que
   abre o lançador sem reconectar sozinho.

## Como validar
```bash
cd projmap/android && npm ci && npm test      # 5 testes do lançador
npm run sync && cd android && ./gradlew assembleDebug
python -m projmap.master --project shows/demo.projmap --no-output --host 0.0.0.0 --token tok123
adb install -r app/build/outputs/apk/debug/app-debug.apk
# no app: IP 10.0.2.2 (emulador) ou o IP do PC (celular), token tok123
```
Validado no emulador API 36:
- conectar por IP + token abre o remote dentro do app;
- tocar em Blackout faz o mestre registrar `blackout: true`;
- a aba Superfícies lista os dados reais do mestre;
- reabrir o app reconecta sozinho;
- o cabeçalho não fica sob a barra de status.

## Critério de aceite
- [x] APK de debug instala e controla o mestre (emulador)
- [x] Build documentado (`projmap/android/README.md`)
- [x] Navegação e HTTP restritos à rede local
- [x] Testes do lançador no CI
- [ ] Testado num celular Android real

## Pendências / próximos
- Validar num celular real (Wi-Fi do local do show).
- APK de release assinado e ícone próprio.
- Scanner de QR ao vivo (ML Kit) se a foto for lenta no uso real.
- mDNS (quando a F2 anunciar o mestre), PJLink e status dos nós no remote.
