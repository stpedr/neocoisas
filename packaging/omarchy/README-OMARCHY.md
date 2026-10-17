# ProjMap — build para Omarchy (Arch Linux / Hyprland)

## Instalar

```bash
tar xzf projmap-*-omarchy-x86_64.tar.gz
cd projmap-*-omarchy-x86_64
./install.sh
```

O instalador:

1. instala pelo `pacman` o `uv`, OpenGL (mesa), libs X11 do XWayland, PortAudio/PulseAudio
   (captura de áudio via PipeWire), `xdg-utils` e `android-tools` (sensor do celular via ADB);
2. copia o app para `~/.local/share/projmap` e cria um venv com Python 3.12 gerenciado pelo `uv`
   (já vem com tkinter para o Lançador);
3. instala as dependências de `requirements-projmap-master.txt`;
4. cria os comandos `projmap`, `projmap-master` e `projmap-node` em `~/.local/bin`
   e o atalho **ProjMap** no menu de apps (Super+Espaço).

A UI do editor já vem compilada (`projmap/ui/out`) — não precisa de Node.js.

Para atualizar, rode o `install.sh` de uma versão nova (o venv e o `.env` são reaproveitados).
Para remover: `~/.local/share/projmap/install.sh --uninstall`.

## Usar

- **Lançador:** Super+Espaço → ProjMap (ou `projmap` no terminal).
- **Direto pelo terminal:**
  `projmap-master --project ~/shows/meu-show.projmap --display auto --open`
- Listar telas/projetores: `cd ~/.local/share/projmap && .venv/bin/python -m projmap.node.screens`

## Dicas para Hyprland

- A saída de projeção usa pyglet via **XWayland** (ativo por padrão no Omarchy).
- Se a janela do projetor não abrir em tela cheia no monitor certo, crie uma regra de janela
  pelo título (a janela se chama `ProjMap · <nó>`) em `~/.config/hypr/hyprland.conf`, trocando
  `HDMI-A-1` pelo nome do projetor em `hyprctl monitors` (a sintaxe exata de `windowrule`
  depende da versão do Hyprland):

  ```
  windowrule = monitor HDMI-A-1, title:^(ProjMap · .*)$
  windowrule = fullscreen, title:^(ProjMap · .*)$
  ```

- Áudio reativo (DJ): captura o monitor do PipeWire; escolha a fonte no painel de áudio.
- Chave da Anthropic (gerador de motions): é guardada no cofre do sistema (`keyring`);
  no Omarchy, o `gnome-keyring` já atende.
