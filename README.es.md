# 🎛️ Athena — Framework Multi-Agente Autoalojado

![Version](https://img.shields.io/badge/version-0.10.1-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**Idiomas:** [Français](README.md) · [English](README.en.md) · Español (este archivo) · [Italiano](README.it.md) · [Deutsch](README.de.md) · [中文](README.zh.md) · [日本語](README.ja.md)

Orquestador de IA "de bajos recursos", ultra-modular, diseñado para funcionar en servidores ligeros o con GPU modestas. Accesible mediante **interfaz web**, **CLI**, **Telegram** y **voz local**.

📖 **[Lee la Guía de Usuario completa](docs/USER_GUIDE.md)** para aprender a instalar, configurar y usar Athena paso a paso.

## ✨ Funciones clave

### 🔐 Multi-Tenant Pro y Colaboración
* **Seguridad y SSO**: autenticación OIDC / OAuth2 para empresas. Registro por invitación gestionado por el administrador.
* **Cifrado en reposo**: las conversaciones y trazas de ejecución almacenadas (SQLite) se cifran en reposo con Fernet (AES-128-CBC + HMAC-SHA256). La clave permanece bajo tu control (`.env` o gestor de secretos externo).
* **Control de costes (cuotas)**: límite automático del gasto de API mediante cuotas diarias de tokens por usuario.
* **Seguridad avanzada**: protección anti-SSRF (DNS rebinding) integrada para la navegación web y enmascaramiento automático de secretos en los registros.
* **Aislamiento absoluto**: cada usuario dispone de su propia memoria (RAG, Core Memory), calendario, listas y presupuesto de API.
* **LLM autoservicio**: cada usuario puede sustituir los modelos globales por sus propias claves API (OpenAI, Anthropic, Gemini, Groq, etc.).
* **Proyectos compartidos**: espacios de trabajo colaborativos con roles detallados (Lector / Editor) y bloqueo de archivos anticolisión.

### 🧠 Motor de orquestación y LLM
* **Multimodelo**: OpenAI, Anthropic, Gemini, Ollama, Groq, Mistral, Qwen, APIs locales compatibles.
* **Swarm (enjambre)**: enrutamiento automático entre agentes especializados (handoffs), ejecución concurrente, debates entre agentes.
* **Pipelines rígidos (opcional)**: forzar una cadena de montaje estricta donde los agentes se encadenan secuencialmente sin desviarse.
* **Arquitectura modular**: backend FastAPI dividido por routers funcionales, respaldado por una base de datos **SQLite** robusta y segura para hilos.
* **Aislamiento de tareas**: estado aislado por ejecución (ContextVars). Las peticiones paralelas nunca interfieren.

### 🌐 Interfaz web avanzada
* **Oficina virtual (isométrica 3D)**: visualización del enjambre, agentes activos resaltados, animaciones de delegación.
* **Cockpit y telemetría**: seguimiento en directo del consumo (tokens, coste por usuario), ejecuciones y errores.
* **Observabilidad**: historial completo y panel de registros en tiempo real para auditar las llamadas a herramientas y el sistema.
* **Mini-IDE integrado**: explorador de archivos **editable** — edición multipestaña (CodeMirror), resaltado, autocompletado, guardado Ctrl+S (solo lectura para Lectores), panel redimensionable y **recarga en vivo** cuando el agente modifica un archivo abierto.
* **Herramientas integradas**: calendario, listas, terminal y galería de medios generados.
* **Configuración sin código**: gestión completa del comportamiento (rutinas, memoria, roles) mediante interfaces claras.

### 🧰 Herramientas y extensibilidad (Skills)
* **Servidores MCP (Model Context Protocol)**: conecta servidores externos sin programar. El conector Home Assistant MCP está incluido localmente para máxima seguridad.
* **Computer Use (RPA 2.0)**: control de un navegador headless interactivo optimizado para LLM.
* **Navegación Git y código**: comprensión de tus repositorios (logs, ramas, edición), ejecución bash/python vía sandbox Docker.
* **Creación de Skills al vuelo**: ¡la IA puede *programar sus propias herramientas* y guardarlas de forma permanente para ampliar sus capacidades!
* **Administración SSH**: gestiona tus servidores remotos mediante comandos SSH.
* **Creatividad y web**: búsqueda web profunda, generación de imágenes/vídeos (Fal, Replicate), scraping.
* **Medios y reuniones**: resumen y transcripción de archivos de audio o reuniones completas.

### 🎨 AthenaDesign Studio
* **Estudio de diseño con IA**: describe lo que quieres y Athena genera y **previsualiza en vivo** interfaces **HTML/CSS/JS**, componentes **React/JSX**, diagramas **Mermaid**, y ejecuta **Python** (presentaciones PowerPoint, gráficos Matplotlib/Plotly) en un **sandbox Docker** aislado.
* **Design System**: aplica tu identidad de marca (colores, tipografía) — manualmente, extrayendo de un CSS, o **importando desde la URL de un sitio**.
* **Importaciones y visión**: adjunta imágenes/documentos (PDF) o captura una página web como referencia; enrutamiento de visión automático (modelo multimodal si está disponible, si no, degradación elegante).
* **Iteración**: anota la vista previa, **sliders WYSIWYG** (color/radio/fuente), versiones, **autocorrección** de scripts con error, exportación a **PDF/PPTX/HTML** y **compartir por enlace** (solo lectura, en sandbox).
* **Proyectos unificados**: un proyecto de Athena contiene tanto el **código** como el **diseño**.

### 🔌 Plugins y autocorrección
* **Pestaña Plugins**: activa extensiones de primer nivel además de los servidores MCP y las skills.
* **Plugin Claude Code**: delega la programación pesada al agente **Claude Code** (CLI), limitado al proyecto activo; se otorga automáticamente al Programador cuando se activa.
* **Autocorrección (self-healing)**: tanto el diseño (Python) como el **Programador** (Code-Test-Fix: `pytest`/`npm test`) corrigen sus errores automáticamente en un bucle acotado.

### 🏠 Domótica y automatizaciones
* **Domótica nativa (Home Assistant)**: lectura de estado y ejecución de acciones (luces, persianas, sensores) al instante.
* **Conciencia espacial**: sabe en qué habitación estás para dirigir sus acciones a tu entorno físico.
* **Rutinas proactivas y flujos**: programación CRON aislada por usuario, disparadores webhook, integraciones avanzadas con **n8n**.
* **Calendario y listas**: sincronización bidireccional con Google Calendar, iCal y CalDAV. Gestión de tareas y listas de la compra.
* **Notificaciones activas**: alertas autónomas de Athena hacia Telegram, Discord, Slack, correo y webhooks.

### 💾 Memoria y aprendizaje
* **Base vectorial RAG**: indexación semántica automática de documentos vía ChromaDB.
* **Grafo de conocimiento y Core Memory**: archivado de hechos duraderos y modelado de relaciones como grafos.
* **Auto-mejora**: retroalimentación de experiencia persistente tras tareas complejas para afinar el comportamiento futuro.
* **Copia de seguridad y restauración**: backup/restore completo del estado (conversaciones, RAG, rutinas, configuraciones).

### 🎙️ Asistente de voz (STT/TTS)
* **100% local y fluido**: síntesis de voz muy rápida con **Kokoro TTS** (API Docker local) y transcripción con **Whisper STT** optimizado.
* **Detección de palabra de activación**: openWakeWord con soporte de "barge-in" (interrumpir la voz de la IA).
* **Satélites ESP32-S3**: conexión directa de satélites de voz ESPHome al framework (S2S), sin pasar por Home Assistant.

## 🚀 Instalación rápida (1 línea)

> [!NOTE]
> *Si este repositorio es privado, necesitas permisos de acceso (token o clave SSH) para que estos comandos funcionen, o puedes clonarlo manualmente.*

**Linux / macOS**: copia y pega este comando en tu terminal:
```bash
curl -sSL https://raw.githubusercontent.com/faelnor92/Athena/main/install.sh | bash
```

**Windows**: ejecuta este comando en PowerShell:
```powershell
iwr -useb https://raw.githubusercontent.com/faelnor92/Athena/main/install.ps1 | iex
```

* **Alternativa Docker Compose**: `docker compose up -d --build`

**Inicio**: `athena start` o `python3 server.py`. Disponible en 👉 **http://localhost:8000/**.

### ⚙️ Despliegue multi-worker (escalado)
El estado mutable compartido (cuentas y cuotas, sesiones de auth, rutinas, invitaciones, proyectos compartidos, configuración por usuario) se almacena en una base SQLite común en modo WAL (`athena_state.sqlite3`) con actualizaciones atómicas — por lo que es **coherente entre varios workers**:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
```
> [!NOTE]
> **RAG en multi-worker.** En modo monoproceso, la base vectorial es embebida (ChromaDB local). Para multi-worker, define **`CHROMA_SERVER_HOST`** (+ `CHROMA_SERVER_PORT`): todos los workers hablan con el mismo servidor ChromaDB (escrituras concurrentes seguras). El `docker-compose.yml` incluido ya trae este servicio `chroma`. El resto del estado es multi-worker-safe de forma nativa.

### 🔒 Seguridad en producción
- **TLS obligatorio**: coloca Athena tras un proxy inverso HTTPS (Caddy, Nginx, Traefik). El servidor emite **HSTS** automáticamente al detectar HTTPS (`X-Forwarded-Proto: https`).
- **Clave de cifrado fuera de `.env`**: para resistir el robo de disco/backup, inyecta `DB_ENCRYPTION_KEY` mediante variable de entorno / gestor de secretos.
- **Cabeceras de seguridad** (CSP, X-Frame-Options, nosniff, Referrer/Permissions-Policy) activas por defecto — `SECURITY_HEADERS=false` para desactivar, `CONTENT_SECURITY_POLICY` para personalizar.
- **Salvaguardas**: throttle anti-fuerza bruta (`LOGIN_MAX_FAILS`/`LOGIN_WINDOW_SECONDS`), rate limiting (`RATE_LIMIT_PER_MIN`, por defecto 300/IP/min), política de contraseñas (`MIN_PASSWORD_LENGTH`, por defecto 8), **registro de auditoría** (`GET /api/audit`, admin) y **validación de admin** de las automatizaciones creadas por cuentas "user".
- **RBAC por herramienta**: `ADMIN_ONLY_TOOLS="execute_bash_command,run_ssh_command,..."` reserva la ejecución de código/comandos a los admins.
- **Contenedor**: la imagen se ejecuta como usuario **no-root** con `HEALTHCHECK`. Auditoría de la instalación: `bash scripts/security_scan.sh`.

### 📡 Observabilidad LLM (opcional — OpenInference / Phoenix)
Además del cockpit integrado, Athena puede exportar **trazas LLM estandarizadas** (OpenInference / OpenTelemetry) a **Phoenix** (Arize). Activación:
```bash
pip install -r requirements-observability.txt
docker compose --profile observability up -d         # Phoenix (UI: http://localhost:6006)
```
luego en `.env`: `OPENINFERENCE_ENABLED=true` y `OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:6006/v1/traces`. Desactivado por defecto.

---

## 🛡️ Comparativa: Athena vs el mercado

> [!NOTE]
> **Metodología.** Comparar lo comparable: **Athena**, **Hermes** y **OpenClaw** son *apps/asistentes alojados*; **CrewAI** y **AutoGen** son *librerías de orquestación* que integras en tu propio código (de ahí los "N/D"). El diferenciador de Athena no es "tener una UI", sino **multi-tenancy + seguridad de nivel empresarial + coding agéntico + observabilidad** en un único producto autoalojado.

| Categoría | Criterio | 🦉 Athena | Hermes Agent | OpenClaw | CrewAI | AutoGen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Interfaz y UX** | **Interfaz gráfica** | **Dashboard web completo (isométrico 3D, grafo nodal, terminal integrado)** | No | Apps companion + Live Canvas | No (CrewAI Studio aparte) | Básica (AutoGen Studio) |
| | **Canales de interacción** | Web, Terminal UI, Telegram, Discord, Slack, Voz | CLI, Telegram, Slack, Discord | **15+ canales** | Código Python | CLI / código |
| | **Integración IDE / dev local** | Consola de código web + Sandbox | No | Sí (asistente local) | Se integra en tu código | Se integra en tu código |
| **Orquestación** | **Modelo multiagente** | **Swarm con enrutamiento semántico automático** | Subagentes aislados paralelos | Enrutamiento multiagente | Secuencial / Jerárquico | Debates / Chat de grupo |
| | **Topologías de grupo** | Debates y handoffs orgánicos | Handoffs aislados | Enrutamiento por canal/agente | Proceso secuencial/jerárquico | **Group chat avanzado** |
| | **Pipelines rígidos** | Sí (cadena de montaje opcional) | Orgánico | — | **Nativo** | Lineal u orgánico |
| | **Persistencia (memoria)** | **Vector DB + historial cifrado entre sesiones** | Sí (SQLite + FTS5) | Sí (sesiones persistentes) | Sí (corto/largo plazo) | Limitado |
| | **Aprendizaje (closed-loop)** | **Skills autogeneradas + RAG de experiencia** | Sí | Herramientas extensibles | No | No |
| | **Herramientas y MCP** | **Nativas + MCP + Home Assistant** | Sí (MCP) | Sí (navegador, canvas, cron, MCP) | Sí (crewai-tools + MCP) | Sí (function calling) |
| **Seguridad global** | **Autenticación** | **Contraseña, tokens, SSO (OIDC)** | No (local) | Básica (local) | N/D | N/D |
| | **Control de acceso (RBAC)** | **Sí (roles Lector/Editor)** | No | No | N/D | N/D |
| | **Cuotas / costes por usuario** | **Sí (cuota de tokens/día + alertas)** | No | No | N/D | N/D |
| **Ejecución y red** | **Sandbox de ejecución** | **Contenedor Docker efímero (recursos limitados)** | Varía | Host | Vía code interpreter | **Sí (Docker)** |
| | **Escudo anti-SSRF** | **Sí (DNS rebinding, bloqueo red interna/metadatos)** | No | No | N/D | N/D |
| **Protección de datos** | **Enmascarado de secretos (logs)** | **Sí** | No | Parcial | N/D | N/D |
| | **Cifrado en reposo** | **Sí (Fernet/AES-128)** | No | Depende del almacenamiento | N/D | N/D |
| | **Aislamiento multi-tenant** | **Sí (memoria/agenda/presupuesto por usuario)** | No | Por workspace | N/D | N/D |
| | **Aprobación humana (HITL)** | **Sí (acciones sensibles interceptadas en la UI)** | Sí (vía chat) | Básica | Hazlo tú mismo | Hazlo tú mismo |

## 📄 Licencia

Distribuido bajo licencia **MIT** — ver [LICENSE](LICENSE). Libre uso, modificación y redistribución.
