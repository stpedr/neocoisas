# ProjMap Remote — app Android (Capacitor)

O app é um **lançador**: pareia com o mestre (QR ou IP + token), lembra o
último mestre e abre na própria WebView o `/remote/` **servido pelo mestre**.
Assim a interface do app sempre corresponde à versão do mestre, e uma
atualização do ProjMap não exige um APK novo.

```
www/index.html + launcher.js   lançador (HTML puro, offline; QR por foto com jsQR)
capacitor.config.json          allowNavigation só p/ IPs privados; user agent "ProjMapApp"
android/                       projeto nativo gerado pelo Capacitor (versionado)
tests/launcher.test.cjs        testes das funções puras (node --test)
```

## Usar

1. No PC: `python -m projmap.master --project shows/meu-show.projmap --host 0.0.0.0`
2. No celular, na mesma Wi-Fi, abra o app e toque em **Escanear QR**. O QR fica
   no card *Remote no celular* do editor. Também dá para digitar o IP e o token
   que o mestre mostra no terminal.
3. Nas próximas vezes o app reconecta sozinho. Use **Trocar mestre** no topo do
   remote para voltar ao lançador.

## Gerar o APK de debug

Requisitos: Node 20+, Android SDK (plataforma 35) e JDK 21. O JDK que vem com o
Android Studio (`jbr`) serve.

```bash
cd projmap/android
npm ci
npm run sync                         # copia o jsQR e sincroniza o projeto nativo
# Windows (Git Bash): export JAVA_HOME="/c/Program Files/Android/Android Studio/jbr"
cd android && ./gradlew assembleDebug
# APK: android/app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Se o Gradle não achar o SDK, crie `android/local.properties` com
`sdk.dir=C:/Users/<você>/AppData/Local/Android/Sdk` (esse arquivo não é
versionado).

**Testar no emulador:** rode o mestre no PC com `--host 0.0.0.0` e, no app,
use o IP `10.0.2.2`, que é o PC visto de dentro do emulador.

## Decisões

- **HTTP puro só na rede local.** O mestre não tem TLS. O Android não aceita
  faixas de IP no `network_security_config`, então o texto claro é liberado no
  app, e a restrição vem de duas camadas: o lançador só aceita 10/8,
  172.16/12, 192.168/16 e localhost, e o `allowNavigation` não navega para
  outros hosts (qualquer outro link abre no navegador do sistema).
- **Câmera** pela WebView (`<input capture>`). O Capacitor pede a permissão
  `CAMERA` em tempo de execução. Serve para a foto da posição do projetor e
  para ler o QR.
- **QR por foto, sem plugin nativo.** O jsQR decodifica no próprio aparelho.
  Um scanner ao vivo (ML Kit) fica para depois, se fizer falta.
- **Sem mDNS por enquanto.** O mestre só anuncia o serviço na F2. Até lá, QR ou
  IP digitado.

## Pendências

- Validar num celular Android real. Até agora foi validado no emulador
  (API 36): conexão, token, comandos e reconexão automática.
- APK de release assinado (keystore fora do git) e ícone próprio.
- Descoberta por mDNS quando a F2 anunciar o mestre na rede.
