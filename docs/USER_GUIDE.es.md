# 📖 Guía de Usuario de Athena

🌍 **Idiomas**: [Français](USER_GUIDE.md) · [English](USER_GUIDE.en.md) · Español · [Italiano](USER_GUIDE.it.md) · [Deutsch](USER_GUIDE.de.md) · [中文](USER_GUIDE.zh.md) · [日本語](USER_GUIDE.ja.md)

¡Bienvenido! Si estás leyendo esta guía, es que acabas de instalar **Athena**, tu director de orquesta de Inteligencia Artificial multiagente. Este documento está pensado para ayudarte a familiarizarte con la herramienta.

---

## 1. 🌟 Primer Inicio y Conexión

Una vez Athena instalado e iniciado en tu máquina, la interfaz gráfica (UI) solo es accesible a través de tu navegador web.

1. Abre tu navegador y ve a la dirección: **`http://localhost:8000`** (o la dirección IP de tu servidor si lo instalaste en otra máquina).
2. Si es el primer inicio, se te pedirá crear una cuenta con una dirección de correo y una contraseña.
3. Una vez conectado, llegas al **Escritorio virtual**.

---

## 2. 💬 Conversar con la IA

Existen **dos formas** de interactuar con Athena: la Interfaz Web y el Terminal (CLI).

### A. Desde la Interfaz Web (UI)
Es el método más visual y sencillo.
- **La vista 3D**: En la página principal verás una representación visual de Athena y sus "Agentes" (el Programador, el Investigador, etc.). Cuando Athena reflexiona o delega una tarea, verás animaciones luminosas que te indican qué agente está trabajando.
- **El Orquestador automático**: En la barra de conversación de abajo, simplemente escribe tu petición. En la Interfaz Web, **siempre hablas con el Orquestador**. Él es lo bastante inteligente para entender tu petición y asignarla automáticamente al agente adecuado (por ejemplo, pasará el relevo al Agente Programador si pides un script).
- **El Explorador de archivos (Workspaces)**: A la izquierda hay un panel con tus archivos. Puedes arrastrar y soltar documentos (PDF, Markdown, código fuente) para que la IA pueda analizarlos.
- **El Editor integrado (mini-IDE)**: haz clic en un archivo para **editarlo** directamente en el navegador — varios archivos abiertos en **pestañas**, resaltado de sintaxis, autocompletado (Ctrl+Espacio) y **guardado** con **Ctrl+S** (💾). Un *Lector* de un proyecto compartido permanece en solo lectura. Puedes **encoger o plegar el explorador** (asa central o botón «◀ Reducir») para ampliar el editor, y cuando el **agente modifica un archivo abierto**, tu vista se **actualiza en directo** (junto con la presencia de los demás lectores).
- **La Consola del Programador (terminal interactivo)**: un verdadero terminal donde hablas con el agente **Programador** para desarrollar. Particularidades:
  - **Proyecto objetivo independiente**: un selector permite programar en un proyecto **diferente** del chat/voz (tus comandos de voz y la domótica siguen en su propio contexto).
  - **Árbol del proyecto** a la derecha (el chat se oculta ahí por innecesario): se **actualiza automáticamente** — ves aparecer los archivos creados por el agente.
  - **IDE en ventana separada**: el botón **«⧉ IDE»** (o un clic en un archivo del árbol) abre el editor en una **ventana real desplazable** (ideal en una 2ª pantalla), con pestañas, resaltado, autocompletado y **Ctrl+S**. *(En el primer uso, permite las ventanas emergentes para el sitio.)*
  - Los comandos con prefijo `$` o `!` se ejecutan directamente como shell; si no, el agente Programador procesa tu petición y **escribe los archivos en el proyecto** (sandbox Docker montada sobre el proyecto).

### C. Proyectos y Colaboración (Workspaces compartidos)
Un **proyecto** es una carpeta de trabajo dedicada. Cuando seleccionas un proyecto en la barra de proyectos (arriba del explorador), **todo lo que hace la IA (lectura, edición de código, terminal, git) queda confinado a esa carpeta** — práctico para aislar un repositorio de código o una carpeta de cliente.
- **Crear / cambiar de proyecto**: botón `＋ Proyecto` y luego selección en la lista. Cada usuario tiene sus propios proyectos, invisibles para los demás.
- **Compartir un proyecto** (botón `👥 Compartir`): como **propietario**, invitas a otros usuarios y eliges su rol:
  - **Lector**: puede consultar y conversar con la IA sobre el proyecto, pero **no puede modificar NADA** — ni siquiera pidiéndoselo al agente (el bloqueo se aplica del lado del servidor, en cada herramienta de escritura: edición de archivo, git, bash, Python). Imposible de eludir.
  - **Editor**: puede modificar los archivos, ejecutar código, hacer commits.
- Solo el propietario puede compartir, cambiar los roles o eliminar el proyecto.

### B. Desde la Consola Interactiva (CLI)
Si prefieres el terminal a la interfaz gráfica, puedes iniciar una conversación de texto puro.
Ve a la carpeta de Athena y escribe:
`python3 athena_cli.py`

> [!TIP]
> **Forzar un agente específico (solo en la Consola)**: A diferencia de la interfaz web donde el Orquestador lo gestiona todo, la consola te permite saltarte al director y hablar directamente con un agente especialista. Para ello, usa:
> `python3 athena_cli.py --agent Codeur`

---

## 3. 🛠️ ¿Qué puede hacer Athena? (Los Superpoderes)

Athena no es un simple "ChatGPT". Es un framework de **agentes de inteligencia artificial autónomos** que integran decenas de herramientas ("Skills") capaces de actuar sobre tu máquina y sobre la web.

### 💻 Código Agéntico (Ingeniería de Software)
Es el corazón del sistema. Athena puede reemplazar a un administrador de sistemas o a un desarrollador:
- **Ejecución de Python y Bash (Sandbox)**: La IA escribe código y lo ejecuta de forma autónoma en un sandbox Docker seguro.
- **Creación de Skills al vuelo**: Funcionalidad única, la IA puede programar nuevas "herramientas" para mejorarse a sí misma, ¡y guardarlas definitivamente en su código fuente base!
- **Administración SSH**: La IA puede conectarse a tus otros servidores remotos vía SSH para hacer mantenimiento.
- **Computer Use (RPA 2.0)**: La IA puede abrir un verdadero navegador web oculto, hacer clic en botones, rellenar formularios y hacer scraping de sitios.
- **Navegación Git y Código**: La IA puede leer tus repositorios Git, entender tu código fuente existente y editarlo en directo.
- **Mantenimiento autónomo**: Un agente nocturno puede verificar y reparar el código fuente automáticamente.

### 🎨 AthenaDesign Studio (Diseño IA)
Un estudio de diseño integrado (pestaña **🎨 Diseño**). Describe lo que quieres crear, Athena lo genera y lo **muestra en directo**:
- **Tipos**: páginas web (HTML/CSS/JS), **apps React** interactivas, **diagramas Mermaid**, y scripts **Python** (presentaciones **PowerPoint**, gráficos). **Plantillas de inicio** (Landing, Pitch deck, Dashboard…) rellenan previamente un prompt.
- **Tu identidad (Design System)**: pliega el panel «Design System» para dar tus colores/tipografía — a mano, pegando un CSS, o vía **«🌐 Desde una URL»** (Athena extrae la identidad de un sitio).
- **Referencias**: adjunta una imagen/un documento (📎) o una página web (🔗) como inspiración.
- **Refinar**: anota la vista previa, ajusta en directo (sliders de color/redondeo/tipografía), recorre las versiones. Si un script Python falla, Athena **se corrige sola**.
- **Compartir / exportar**: botón **Compartir** (enlace de solo lectura), **Exportar PDF**, y descarga de los `.pptx`.
- *Consejo*: un proyecto Athena reúne **código y diseño** — gestionas ambos en el mismo lugar.

### 🔌 Plugins (incluido Claude Code)
En **Ajustes > 🔌 Plugins**, activa extensiones. El **plugin Claude Code** recurre al agente de código **Claude Code** (hace falta el CLI `claude` instalado y conectado): una vez activado, tu **Programador** puede delegarle las tareas de código complejas, directamente en el proyecto activo. *(Consume tu suscripción/clave de Claude.)*

### 🏠 Domótica, Contexto y Día a Día
- **Domótica Nativa (Home Assistant)**: La IA se conecta directamente a tu domótica. Pídele *"Apaga la luz del salón"* o *"Baja las persianas"* y lo hace al instante.
- **Extensiones MCP (Avanzado)**: Athena soporta el protocolo MCP. Esto le permite conectar plugins complejos (como un acceso profundo a la base de datos de Home Assistant para crear automatizaciones, o cualquier otro servidor MCP existente).
- **Conciencia Espacial**: La IA puede saber en qué habitación te encuentras (si tienes sensores) para adaptar sus acciones (p. ej., *"Enciende la luz"* encenderá la de la habitación donde estás).
- **Tiempo y Clima**: Previsiones meteorológicas de varios días y sincronización temporal.
- **Listas y Compras**: Pídele que añada leche a tu lista de la compra o que cree una lista de tareas.

### 📅 Productividad y Comunicación
- **Agenda y Planificación**: Sincronización con tus calendarios (iCal, CalDAV) para leer y crear eventos.
- **Resúmenes de Reuniones**: Capacidad de transcribir y resumir reuniones o archivos de audio.
- **Notificaciones**: Athena puede enviarte mensajes por iniciativa propia en Telegram, Discord o Slack.
- **Generación de Medios**: Creación de imágenes (vía API Fal/Replicate) y manipulación de archivos (PDF, documentos).
- **Workflows (n8n)**: Disparo de escenarios complejos vía webhooks n8n.

### ⏰ Rutinas Proactivas
Athena no espera a que le hables. Pídele: *"Hazme un resumen de mi día cada mañana a las 7:30"*. Se despertará sola, analizará tu agenda, el clima, el estado de tu casa, ¡e incluso podrá poner en marcha la cafetera!

---

## 4. ⚙️ Entender los Parámetros de la Interfaz

Al hacer clic en el icono del engranaje (⚙️) de la barra lateral, accedes a los ajustes de tu perfil. **Cada parámetro está estrictamente aislado para tu usuario.**

### Pestaña "🔑 Claves API" (Mi Modelo y Claves LLM)
- **Proveedor de IA (Ej: OpenAI, Anthropic, Ollama)** y **Nombre del Modelo**: Elige la versión de la IA que deseas utilizar.
- **Clave API Personal**: Si este campo está relleno, Athena usará TU clave para funcionar, y se te facturará en tu propia cuenta de desarrollador. Esto permite anular el modelo por defecto del servidor.
- **📊 Mi uso**: justo debajo de tus claves, un resumen de tu consumo personal (peticiones, tokens, coste €) de hoy, los últimos 30 días y en total — para seguir tus gastos de un vistazo. (Un administrador, por su parte, ve el consumo de todas las cuentas.)

### 🔐 Asegurar mi cuenta (pestaña «Usuarios»)
- **Mi contraseña**: cámbiala cuando quieras (mín. 8 caracteres). Por seguridad, cambiar tu contraseña **desconecta tus otras sesiones**.
- **Autenticación de dos factores (2FA)**: haz clic en **Activar la 2FA**, añade la cuenta a tu aplicación de autenticación (Google Authenticator, Authy, FreeOTP…) escaneando/introduciendo el secreto mostrado, luego introduce un código para confirmar. En cada conexión se te pedirá entonces un **código temporal** además de la contraseña. Puedes desactivarla en cualquier momento (se requiere un código para confirmar).
  - *¿Dispositivo perdido?* Un administrador puede reiniciar tu 2FA para devolverte el acceso.

### Pestaña "Agenda y Todo"
- **Agenda Principal (URL)**: Pega la dirección de un flujo iCal (Google Calendar). La IA podrá entonces leer tu planificación.
- **Servidor CalDAV (URL, Usuario, Contraseña)**: Si usas una agenda avanzada (Nextcloud, Synology), la IA podrá *crear* y *modificar* eventos directamente.

### Pestaña "Comportamiento y Seguridad" (El Cerebro de Athena)
Es la sección más importante para ajustar el comportamiento global y las seguridades de la máquina. Está dividida en varias subsecciones:

#### 1. Ejecución y salvaguardas
- `Sandbox de ejecución de código/comandos`: Elige **Docker** (recomendado) para que la IA ejecute sus scripts en un sandbox seguro, o **Local** si quieres que actúe directamente sobre tu sistema operativo.
- `Auto-mejora`: Autoriza a la IA a sacar lecciones de sus fracasos para crear reglas de comportamiento futuras.
- `Presupuestos (Tiempo y Tokens)`: Salvaguardas financieras. Permite limitar el número máximo de segundos (0 = infinito) o el número máximo de tokens que la IA tiene derecho a consumir por tarea.
- `Alerta de coste del día`: Si el gasto diario supera este umbral en euros, recibirás una notificación.

#### 2. Seguridad
- `Auto-aprobar las herramientas sensibles`: Por defecto (sin marcar), la IA siempre te pedirá una confirmación antes de usar una herramienta marcada como "sensible" (p. ej., escribir en un archivo de sistema). Si lo marcas, la IA se vuelve totalmente autónoma (bajo tu propia responsabilidad).
- `Contraseña de admin / Orígenes CORS`: Aseguramiento del servidor web para impedir conexiones externas no deseadas.
- `Duración de validez de una sesión`: Tiempo (en horas) antes de ser desconectado de la interfaz (por defecto: 168h, es decir, una semana).
- `Cuotas y Límites`: El sistema protege tus finanzas. Un administrador puede definir un límite de consumo de tokens por día en la base de los usuarios.
- `Cifrado en reposo`: Las conversaciones y los registros de ejecución están cifrados en base (SQLite) vía Fernet (AES-128-CBC + HMAC). La clave se almacena en el `.env` de tu instalación — **no la pierdas** (si no, el historial cifrado se vuelve ilegible), y para una protección real contra el robo de disco, consérvala fuera de la carpeta (variable de entorno inyectada / gestor de secretos).
- `Protecciones integradas (invisibles)`: Athena enmascara automáticamente tus claves API y secretos en los logs (Redaction) e integra una protección anti-SSRF que bloquea las peticiones web hacia tu red interna o tus metadatos Cloud.

#### 3. Orquestación y agentes (avanzado)
- `Enrutamiento LLM (Delegation Router)`: El Orquestador lee tu mensaje y elige el agente adecuado.
- `Modelo rápido`: Puedes forzar un modelo muy rápido (p. ej., `gpt-4o-mini` o `haiku`) solo para las decisiones de enrutamiento, lo que hace la IA más reactiva.
- `Modelos de repliegue (Fallback)`: Si la API de tu IA principal falla, Athena intentará usar estos modelos de respaldo.
- `Caché de prompt`: Tecnología que permite ahorrar dinero y tiempo en las conversaciones largas.
- `Auto-crítica`: Si está activada, la IA relee y verifica su propia respuesta antes de enviártela.

#### 4. Memoria
- `Base de hechos (Core Memory)`: Lista todo lo que Athena ha aprendido sobre ti de forma permanente (tus gustos, tu oficio). Puedes eliminar elementos ahí.
- `Knowledge Graph`: Además de los hechos simples, la IA construye una red de relaciones ("Grafo") entre las entidades para entender mejor tu contexto.
- `Compactación más allá de N mensajes`: Para evitar disparar la factura, Athena resume automáticamente las partes antiguas de la conversación al cabo de N mensajes (40 por defecto).
- `Mensajes recientes guardados al pie de la letra`: Athena siempre guarda los últimos N intercambios estrictos en memoria a corto plazo (12 por defecto).

#### 5. Voz expresiva
- `Emociones vocales`: ¡El LLM inserta etiquetas `[laugh]`, `[sad]` en sus textos, y el motor vocal adapta su tono!
- `Servidor TTS expresivo y Voz`: Si usas un motor vocal de terceros (como XTTS), indica aquí su dirección IP.

#### 6. Conciencia Espacial (Presencia / follow-me)
- `Entidad HA de habitación actual`: Si tienes detectores de presencia en Home Assistant, indica aquí la entidad (p. ej., `sensor.habitacion_actual`). La IA sabrá entonces en qué habitación estás para encender la luz adecuada o adaptar su comportamiento.

#### 7. Automatización (n8n)
- `Workflows autorizados`: Puedes conectar Athena a automatizaciones n8n complejas dándole acceso a direcciones web (Webhooks).

### Las demás Pestañas del Panel de Ajustes
Además de "Comportamiento", la barra lateral de ajustes te da acceso a otros menús especializados:

* **Pestaña "Conocimientos (RAG)"**: Aquí es donde puedes pedir a la IA que analice (o purgue) los documentos que has colocado en el Explorador de archivos.
* **Pestaña "Rutinas"**: Permite programar tareas automáticas (p. ej., "Haz el resumen de la casa todos los días a las 7:00"). También puedes recuperar ahí las direcciones "Webhooks" de estas rutinas, o hacer que una rutina **dispare un Workflow** determinista (campo «Workflow» del formulario) en lugar de una simple tarea.
* **Pestaña "Satélites Vocales"**: Permite configurar los altavoces ESP32 conectados a Athena.
* **Pestaña "Extensiones MCP"**: Permite conectar plugins externos estándar (p. ej., conector GitHub, conector Home Assistant) a la IA.
* **Pestaña "Diagnósticos y Sistema"**: Verifica la salud de la instalación (base de datos, STT, TTS). Aquí es donde se encuentra el botón de emergencia **Reiniciar el motor Vocal (Kokoro)** en caso de fallo de sonido, así como las opciones de **Copia de seguridad y Restauración** de tu entorno completo.
* **Pestaña "Workflows"**: Crea **pipelines deterministas** (cadena de agentes, tipo "línea de montaje") como alternativa al modo autónomo — útil cuando se quiere un desarrollo reproducible y auditable. Ver la sección dedicada más abajo.
* **Pestaña "Usuarios" (Admin)**: Si eres administrador, aquí puedes invitar a nuevas personas, gestionar sus derechos y sus cuotas de tokens. También **validas las automatizaciones** (workflows/rutinas) creadas por las cuentas "usuario" antes de que puedan ejecutarse, puedes **reiniciar la 2FA** de una cuenta (dispositivo perdido), y consultar el **registro de auditoría** (conexiones, cambios de contraseña, validaciones…) vía `GET /api/audit`.

---

## 5. 💻 Gestionar el Servidor (Comandos de Administración)

Si eres el administrador de la máquina que aloja Athena, dispones de potentes comandos de sistema para gestionar el ciclo de vida del servidor.

### 🍎 Linux y macOS
Abre tu Terminal. El comando principal se llama `athena`.
- `athena start`: Enciende la IA en segundo plano (proceso SystemD / LaunchAgent).
- `athena stop`: Apaga el servidor limpiamente.
- `athena restart`: Reinicia completamente la aplicación.
- `athena status`: Verifica si el servidor está bien en línea.
- `athena logs`: Muestra el registro técnico del servidor en tiempo real. (Pulsa `Ctrl+C` para salir).

**Actualizar el software:**
Ve a la carpeta del código fuente y lanza: `./update.sh`

### 🪟 Windows (PowerShell)
Abre PowerShell. El comando de administración termina en `.ps1`.
- `athena.ps1 start`: Inicia el servidor en tarea de fondo.
- `athena.ps1 stop`: Corta el servidor.
- `athena.ps1 restart`: Reinicia el proceso.
- `athena.ps1 status`: Muestra el estado.
- `athena.ps1 logs`: Muestra la consola técnica del orquestador.

**Actualizar el software:**
Ve a la carpeta del código fuente y lanza: `.\update.ps1`
