<img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='72' height='72' viewBox='0 0 28 28'%3E%3Crect x='1' y='1' width='26' height='26' rx='8' fill='%231a222d' stroke='%237fb4ff' stroke-width='1.5'/%3E%3Ctext x='14' y='19.5' text-anchor='middle' font-family='-apple-system,Helvetica,Arial,sans-serif' font-weight='700' font-size='14' fill='%237fb4ff'%3ER%3C/text%3E%3C/svg%3E" width="56" height="56" align="left" alt="" />

# Rensi Dashboard

Uso de Claude Code, en vivo, autoalojado.

[English](README.md) · **Español**

<br clear="left"/>

[![License: MIT](https://img.shields.io/badge/license-MIT-4ad99b.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/breisnerlopez/rensi-claude-dashboard?color=7fb4ff)](https://github.com/breisnerlopez/rensi-claude-dashboard/releases/latest)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-bd9bff.svg)](pyproject.toml)

Escucha solo en `127.0.0.1` por defecto. Lee transcripts locales de Claude Code — nada sale de tu máquina.

<!-- screenshot: corre `rensi-dashboard start`, abre http://127.0.0.1:7681, captura
     el gauge principal + tarjetas de conversación, guarda como
     .github/assets/screenshot.png y descomenta la línea de abajo. -->
<!-- ![Captura de Rensi Dashboard](.github/assets/screenshot.png) -->

Dashboard autoalojado para el uso de [Claude Code](https://claude.com/claude-code): límites oficiales de 5 horas y semanales, estimaciones de tokens/costo por proyecto, y una **vista en vivo de cada sesión en curso** — subagentes activos, workflows con sus fases, tareas abiertas y un timeline completo de uso de herramientas, actualizado de forma independiente en un ciclo rápido de ~15s.

Si te sirve, **una estrella ayuda a que otros lo encuentren** → ver el link al final.

## Empezar (2 comandos, listo en minutos)

Funciona en **Linux, macOS y Windows**. Sin cuenta, sin archivo de configuración que editar a mano — el instalador genera un token de acceso, arranca el dashboard y lo abre en tu navegador.

**Linux / macOS:**
```bash
curl -fsSL https://github.com/breisnerlopez/rensi-claude-dashboard/releases/latest/download/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://github.com/breisnerlopez/rensi-claude-dashboard/releases/latest/download/install.ps1 | iex
```

Con eso basta — el script instala Python si no lo tienes, instala el dashboard vía [pipx](https://pipx.pypa.io/), lo registra para arrancar solo (servicio de usuario systemd / crontab en Linux, Programador de tareas en Windows), y abre `http://127.0.0.1:7681` con tu token de acceso.

Estos comandos de una línea siempre traen un **release etiquetado**, nunca la rama `main` (que puede cambiar) — cada release incluye un archivo [`SHA256SUMS`](../../releases/latest) para verificar la descarga si quieres. ¿Prefieres leer el script antes de pasarlo a una shell? Es una decisión completamente razonable — tómalo de la [página del último release](../../releases/latest), o lee [`install.sh`](install.sh) / [`install.ps1`](install.ps1) directo en el repo.

Una vez instalado:
```bash
rensi-dashboard status   # si está corriendo, y la URL
rensi-dashboard stop     # detenerlo
rensi-dashboard restart  # reiniciarlo
```

Opcional, para los porcentajes oficiales de límite de uso (funciona sin esto también, en modo solo-estimación-local):
```bash
pipx inject rensi-claude-dashboard claude-monitor
```

## Qué muestra

- **Bloque de 5h / Semana** — los porcentajes oficiales de límite de uso, directo de la API de uso de Anthropic (los mismos números que claude.ai), con una proyección de sostenibilidad ("a este ritmo te quedan ~N días").
- **Conversaciones** — una tarjeta por proyecto activo/reciente: modelo + versión, tamaño y ocupación de la ventana de contexto, estimación de costo, y una línea de estado ("5/6 tareas · 1 subagente en curso · 1 workflow en curso").
- **Detalle de sesión** (toca/clic una tarjeta) — detalle completo de esa sesión: tareas con estado y bloqueos, subagentes con su descripción y estado, workflows con su pipeline de fases, un histograma de herramientas usadas, y un timeline de actividad con scroll. En pantalla ancha se abre como un panel anclado a la derecha con columna de estado y columna de actividad con scroll independiente; en el celular es una hoja a pantalla completa.
- **Hoy / Esta semana / Historial** — tendencias de tokens y costo en el tiempo.

Todo excepto los dos porcentajes oficiales está etiquetado explícitamente como estimación local. La interfaz sigue el idioma de tu navegador automáticamente (inglés/español hoy — ver [Contribuir](#contribuir) para agregar otro).

## En qué se diferencia

La propia página de uso de claude.ai muestra tus límites oficiales — este dashboard muestra los mismos números oficiales (no los estima ni adivina) más lo que claude.ai no muestra: una vista en vivo de qué está corriendo realmente en tus proyectos ahora mismo, y un desglose local de costo/tokens por proyecto. Los porcentajes oficiales vienen de la API de uso de Anthropic vía el CLI opcional [`claude-monitor`](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor); sin él, el dashboard sigue funcionando, solo sin esos dos números.

## Arquitectura

```
rensi_dashboard/
  core.py       -- cada ruta/bind/token, resuelto desde variables de entorno
                    con valores por defecto portables entre SO (platformdirs).
                    Ningún literal de una máquina específica en otro lado.
  aggregate.py   -- parsea ~/.claude/projects/**/*.jsonl, opcionalmente llama
                    a la API oficial de uso (vía claude-monitor, si está
                    instalado), escribe data.json + session/<slug>.json.
  server.py      -- http.server de la librería estándar, rutas en whitelist
                    únicamente. Auth por secreto compartido (header / cookie /
                    query param de un solo uso), se niega a arrancar sin
                    token. Puede correr su propio scheduler en proceso (dos
                    hilos daemon, 180s/15s) para que un solo proceso alcance
                    en cualquier SO.
  cli.py         -- `rensi-dashboard setup|start|stop|status|restart` y
                    `rensi-dashboard aggregate [--fast]` para quien prefiera
                    manejar el scheduling por su cuenta (timers de systemd,
                    cron, Programador de tareas) en vez del scheduler
                    incorporado.
  web/index.html -- todo el frontend. Sin build step, sin framework.
```

Dos formas de correrlo:
- **`rensi-dashboard start`** (lo que configura el instalador) — un proceso, scheduler en proceso, funciona igual en Windows/Mac/Linux.
- **Tu propio scheduler** — corre `rensi-dashboard aggregate` / `rensi-dashboard aggregate --fast` con la cadencia que quieras (timers de systemd, cron, Programador de tareas) y `python3 -m rensi_dashboard.server --no-scheduler` como servicio supervisado. Así corre la propia instancia del mantenedor, detrás de Traefik + Authentik forward-auth — ver `--no-scheduler` en `server.py` si quieres ese estilo.

## Seguridad

Este dashboard lee transcripts locales de Claude Code, que pueden contener detalle sensible del negocio (nombres de proyecto, rutas de archivo, comandos). Por defecto escucha solo en `127.0.0.1` — nada fuera de tu máquina puede alcanzarlo a menos que configures `DASHBOARD_BIND` explícitamente. Cada solicitud necesita el token de acceso (header, cookie, o el link `?t=` de un solo uso que imprime el instalador — que se borra de la barra de direcciones en cuanto se fija la cookie).

Si pones un reverse proxy delante (por ejemplo para acceso remoto), que el proxy maneje la autenticación real y deja el chequeo de token como segunda capa — `server.py` se niega directamente a arrancar si no hay token configurado, así que no puede quedar abierto por accidente.

Un redactor basado en regex elimina formatos comunes de secretos (API keys, tokens, bloques PEM) y rutas de archivo de todo lo que se escribe a disco. Es una red de mejor esfuerzo, no una garantía — no amplíes `DASHBOARD_BIND` a `0.0.0.0` sin algo más que controle el acceso.

**Notas de plataforma:** el indicador en vivo de "sesión activa" (un proceso `claude --remote-control` corriendo) es solo-Linux en v1 — simplemente no se enciende aún en Windows/Mac, todo lo demás funciona igual. El panel de límite oficial necesita la dependencia opcional `claude-monitor`; sin ella el dashboard funciona bien en modo solo-estimación-local.

## Configuración manual / avanzada

Variables de entorno (todas opcionales, con valores por defecto sensatos):

| Variable | Por defecto | Significado |
|---|---|---|
| `DASHBOARD_BIND` | `127.0.0.1` | interfaz en la que escuchar |
| `DASHBOARD_PORT` | `7681` | puerto |
| `DASHBOARD_TOKEN` | autogenerado, persistido | token de acceso |
| `DASHBOARD_DATA_DIR` | directorio de datos de app según el SO | dónde viven data.json/session/*.json/cache |
| `CLAUDE_HOME` | `$HOME` | dónde se leen `.claude/projects` y `.claude/tasks` |
| `DASHBOARD_TZ` | `UTC` | zona horaria usada para los límites de día/bloque |
| `DASHBOARD_FULL_INTERVAL` / `DASHBOARD_FAST_INTERVAL` | `180` / `15` (segundos) | cadencia del scheduler en proceso |

## Contribuir

Esta es una herramienta pequeña, mantenida por una sola persona — issues y pull requests son bienvenidos, sin ceremonia de proceso. Para correrlo localmente: `pip install -e .` en un virtualenv, luego `rensi-dashboard start --foreground`. Ver [CONTRIBUTING.md](CONTRIBUTING.md) (en inglés), incluyendo cómo agregar un idioma a la interfaz (diccionario `STRINGS` en `rensi_dashboard/web/index.html`).

## Licencia

MIT — ver [LICENSE](LICENSE).

---

Hecho por [Breisner Lopez](https://breisner.info) ("Rensi") · [GitHub](https://github.com/breisnerlopez)

⭐ **Si esto te sirve, darle estrella es la forma más simple de decirlo** — así otras personas encuentran herramientas pequeñas como esta.

[English](README.md) · **Español**

<!-- i18n-sync: README.md@b392931 -->
