

# FrameBub - Bot de Datos de Frames para Juegos de Lucha

Un bot de Discord que proporciona datos de frames instantáneos, imágenes de hitboxes, rutas de combos y desafíos de cuestionarios para 8 juegos de lucha mediante consultas en lenguaje natural o menús interactivos.

## Características

- **Búsqueda en Lenguaje Natural** - Haz preguntas como `what is the framedata for ryu's fireball? ` o `Ryu vs ken 5hp` en inglés
- **8 Juegos Compatibles** - SF6, SFV, GGST, 2XKO, BBCF, COTW, Third Strike y MK1, con más por venir
- **Imágenes de Hitbox y GIF** - Activa o desactiva las imágenes de hitbox y gifs.
- **Comparar Movimientos** - Presiona Compare para elegir un segundo movimiento y ver ambos lado a lado
- **Menú Interactivo** - `/bub` abre un selector de personajes y movimientos para cada juego
- **Comandos con Slash** - Comandos dedicados `/sf6`, `/ggst`, `/sfv`, `/2xko`, `/bbcf`, `/cotw`, `/third-strike`, `/mk1`
- **Modo Cuestionario** - Pon a prueba tus conocimientos con cuestionarios de datos de frames de fácil, medio y difícil para todos los juegos
- **Recordatorios** - Establece recordatorios con soporte de zona horaria
- **Alternar Notas** - Visualiza notas específicas de movimientos procedentes de wikis de la comunidad y fuentes de datos de frames

## Juegos Compatibles

| Juego | Fuente | Notas |
|------|--------|-------|
| Street Fighter 6 | FAT ODS | GIFs de hitbox locales, imágenes de SuperCombo |
| Street Fighter V | FAT ODS | Filas separadas para V-Trigger, imágenes de SuperCombo |
| Guilty Gear Strive | Dustloop ODS | Imágenes de hitbox, movimientos específicos de estado (Installs, Blood, etc.) |
| 2XKO | Community ODS | Imágenes y hitboxes procedentes de wikis |
| BlazBlue Central Fiction | Dustloop ODS | Imágenes de hitbox, notas de movimientos |
| City of the Wolves | DreamCancel ODS | Imágenes de movimientos normales (no hay imágenes de hitbox disponibles) |
| Third Strike | SuperCombo ODS | Imágenes de hitbox, movimientos versionados |
| Mortal Kombat 1 | Kombat Akademy | Personajes jugables, Kameos, rutas de combos |

## Capturas de Pantalla

| Lenguaje Natural | Sistema de Menús | Tabla de Datos de Frames |
|:---:|:---:|:---:|
| <img width="400" alt="Consultas en lenguaje natural" src="https://github.com/user-attachments/assets/83ffd010-2605-4d66-97ae-09f8ed18bff9" /> | <img width="400" alt="Menú de Bub" src="https://github.com/user-attachments/assets/099056f2-a4f4-480f-97d6-c7f1f064b977" /> | <img width="400" alt="Tabla de datos de frames" src="https://github.com/user-attachments/assets/afe309e9-efb6-4efb-854a-f57b1cd575f6" /> |
| <img width="400" alt="Consulta en lenguaje natural 2" src="https://github.com/user-attachments/assets/eb99c148-fcb1-4db9-9db7-a43b26fafb9c" /> | <img width="400" alt="Selección de juego en menú" src="https://github.com/user-attachments/assets/dadbef81-8e10-4f51-8ba1-2b24f7e2584e" /> | <img width="400" alt="Tabla de datos de frames 2" src="https://github.com/user-attachments/assets/d6d93bf6-ff69-467e-a328-70a74c9e55c1" /> |
| <img width="400" alt="Consulta en lenguaje natural 3" src="https://github.com/user-attachments/assets/7105b5dc-d411-4096-8427-1b31b46e5880" /> | <img width="400" alt="Selección de personaje en menú" src="https://github.com/user-attachments/assets/1d54d8b2-e13a-46ee-b553-dc6504e03214" /> | <img width="400" alt="Tabla de datos de frames 3" src="https://github.com/user-attachments/assets/5cbe2769-0886-4926-9ef9-bf8c2fb253c8" /> |

## Referencia Rápida

### Ejemplos en Lenguaje Natural
```
@bub ryu 5hp framedata
@bub ken fireball gif
@bub mai ex fan
@bub delete carl 5c framedata
@bub 3s urien 5hp and 2mk
@bub mk1 sub 1 framedata
@bub ahri 5l vs ken 5p
```

### Comandos con Slash
| Comando | Ejemplo |
|---------|---------|
| `/sf6` | `char_name: Ryu` `move_name: 236LP` |
| `/ggst` | `char_name: Ky` `move_name: 5H` |
| `/sfv` | `char_name: Ryu` `move_name: 5MP` |
| `/2xko` | `char_name: Ahri` `move_name: 5L` |
| `/bbcf` | `char_name: Ragna` `move_name: 5B` |
| `/cotw` | `char_name: Ronaldo` `move_name: Far C` |
| `/third-strike` | `char_name: Urien` `move_name: 5HP` |
| `/mk1` | `char_name: Sub-Zero` `move_name: 1` |

## Configuración

### Requisitos Previos
- Python 3.9+
- Token de bot de Discord
- Archivos ODS de datos de frames (incluidos en el repositorio)

### Instalación
```bash
git clone <repo-url>
cd bub-but
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Configuración
Crea un archivo `.env`:
```
DISCORD_TOKEN=your_bot_token_here
```

### Ejecución
```bash
python bot.py
```

## Estructura del Proyecto

```
bubbot/
  runtime/          # Bot entrypoint, message routing, slash commands
  frame_data/       # Per-game parsers, embeds, and lookup helpers
  features/         # Quiz, menu, reminders
  data/             # Alias maps, generated image caches
  utils/            # Shared text, comparison, Discord helpers
scripts/            # Cache builders and scrapers
regressions/        # Focused regression tests
mk1/                # MK1 JSON source data
*.ods               # Frame data source files (one per game)
```

## Licencia

MIT
