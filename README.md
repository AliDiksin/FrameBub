# FrameBub - Fighting Game Frame Data Bot

A Discord bot that provides instant frame data, hitbox images, combo routes, and quiz challenges for 9 fighting games using natural language queries or interactive menus.

## Features

- **Natural Language Lookup** - Ask questions like `what is the framedata for ryu's fireball? ` or `Ryu vs ken 5hp` in plain English
- **9 Supported Games** - SF6, SFV, USF4, GGST, 2XKO, BBCF, COTW, Third Strike, and MK1 with more to come
- **Hitbox & GIF Images** - Toggle hitbox images and gifs.
- **Compare Moves** - Press Compare to pick a second move and view both side by side
- **Interactive Menu** - `/bub` opens a character and move selector for every game
- **Slash Commands** - Dedicated `/sf6`, `/usf4`, `/ggst`, `/sfv`, `/2xko`, `/bbcf`, `/cotw`, `/third-strike`, `/mk1` commands
- **Quiz Mode** - Test your knowledge with easy, medium, and hard frame data quizzes across all games
- **Reminders** - Set reminders with timezone support
- **Notes Toggle** - View move-specific notes from community wikis and frame data sources

## Supported Games

| Game | Source | Notes |
|------|--------|-------|
| Street Fighter 6 | FAT ODS | Local hitbox GIFs, SuperCombo images |
| Street Fighter V | FAT ODS | V-Trigger separated rows, SuperCombo images |
| Ultra Street Fighter IV | SuperCombo ODS | 44-character roster, source notes, available move images |
| Guilty Gear Strive | Dustloop ODS | Hitbox images, state-specific moves (Installs, Blood, etc.) |
| 2XKO | Community ODS | Wiki-sourced images and hitboxes |
| BlazBlue Central Fiction | Dustloop ODS | Hitbox images, move notes |
| City of the Wolves | DreamCancel ODS | Regular move images (no hitbox images available) |
| Third Strike | SuperCombo ODS | Hitbox images, versioned moves |
| Mortal Kombat 1 | Kombat Akademy | Playable characters, Kameos, combo routes |

## Screenshots

| Natural Language | Menu System | Frame Data Table |
|:---:|:---:|:---:|
| <img width="400" alt="Natural language queries" src="https://github.com/user-attachments/assets/83ffd010-2605-4d66-97ae-09f8ed18bff9" /> | <img width="400" alt="Bub menu" src="https://github.com/user-attachments/assets/099056f2-a4f4-480f-97d6-c7f1f064b977" /> | <img width="400" alt="Frame data table" src="https://github.com/user-attachments/assets/afe309e9-efb6-4efb-854a-f57b1cd575f6" /> |
| <img width="400" alt="Natural language query 2" src="https://github.com/user-attachments/assets/eb99c148-fcb1-4db9-9db7-a43b26fafb9c" /> | <img width="400" alt="Menu game select" src="https://github.com/user-attachments/assets/dadbef81-8e10-4f51-8ba1-2b24f7e2584e" /> | <img width="400" alt="Frame data table 2" src="https://github.com/user-attachments/assets/d6d93bf6-ff69-467e-a328-70a74c9e55c1" /> |
| <img width="400" alt="Natural language query 3" src="https://github.com/user-attachments/assets/7105b5dc-d411-4096-8427-1b31b46e5880" /> | <img width="400" alt="Menu character select" src="https://github.com/user-attachments/assets/1d54d8b2-e13a-46ee-b553-dc6504e03214" /> | <img width="400" alt="Frame data table 3" src="https://github.com/user-attachments/assets/5cbe2769-0886-4926-9ef9-bf8c2fb253c8" /> |

## Quick Reference

### Natural Language Examples
```
@bub ryu 5hp framedata
@bub ken fireball gif
@bub mai ex fan
@bub delete carl 5c framedata
@bub 3s urien 5hp and 2mk
@bub usf4 cammy cannon spike lk framedata
@bub mk1 sub 1 framedata
@bub ahri 5l vs ken 5p
```

### Slash Commands
| Command | Example |
|---------|---------|
| `/sf6` | `char_name: Ryu` `move_name: 236LP` |
| `/ggst` | `char_name: Ky` `move_name: 5H` |
| `/sfv` | `char_name: Ryu` `move_name: 5MP` |
| `/2xko` | `char_name: Ahri` `move_name: 5L` |
| `/bbcf` | `char_name: Ragna` `move_name: 5B` |
| `/cotw` | `char_name: Ronaldo` `move_name: Far C` |
| `/third-strike` | `char_name: Urien` `move_name: 5HP` |
| `/usf4` | `char_name: Cammy` `move_name: Cannon Spike (623 LK)` |
| `/mk1` | `char_name: Sub-Zero` `move_name: 1` |

## Setup

### Prerequisites
- Python 3.9+
- Discord bot token
- ODS frame data files (included in repo)

### Installation
```bash
git clone <repo-url>
cd bub-but
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Configuration
Create a `.env` file:
```
DISCORD_TOKEN=your_bot_token_here
```

### Running
```bash
python bot.py
```

## Project Structure

```
bubbot/
  runtime/          # Bot entrypoint, message routing, slash commands
  frame_data/       # Per-game parsers, embeds, and lookup helpers
  features/         # Quiz, menu, reminders
  data/             # Alias maps, generated image caches
  utils/            # Shared text, comparison, Discord helpers
scripts/            # Cache builders and scrapers
mk1/                # MK1 JSON source data
*.ods               # Frame data source files (one per game)
```

## License

MIT
