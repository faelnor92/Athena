import os
import re
import json
import httpx

# System instructions to guide the LLM to think like Claude Design / Open Design
SYSTEM_PROMPT = """You are AthenaDesign, an elite AI design companion. Your goal is to generate beautiful, interactive, and premium visual interfaces or Python scripts based on user requests.

Your output must be structured using these XML-like tags to allow the application to parse it:
<artifact_type>html or python</artifact_type>
<artifact_explanation>A brief, friendly description of your design choices and how to interact with it.</artifact_explanation>
<artifact_code>
[Insert the complete code here. Do not truncate. Do not include markdown code block formatting like ```html inside these tags.]
</artifact_code>

DESIGN RULES:
1. VISUAL EXCELLENCE: Never use plain basic colors (red, blue, green). Use a curated palette like HSL, Tailwinds-like hues (Slate, Zinc, Indigo, Violet, Rose, Emerald).
2. MODERN STYLING: Always use clean layout structures, round borders, beautiful typography (Google Fonts Outfit or Inter), smooth gradients, and glassmorphic panels (backdrop-filter: blur).
3. MICRO-ANIMATIONS: Include subtle hover states (scale, shadows, glow), smooth transitions, or keyframe animations.
4. JAVASCRIPT: For HTML designs, make them interactive! Use CDNs for Chart.js, Lucide Icons, or FontAwesome if needed. Keep the script clean.
5. PYTHON CODE: For Python artifacts, write code that generates useful data, charts, simulations (using Matplotlib/Plotly) or programmatically constructs PowerPoint presentations (using python-pptx) saving them to the local directory. Set matplotlib styling to look clean and modern (gridlines, nice colors, no ugly grey backgrounds). Always end with plt.show() or fig.show() to render the preview if using charts.
6. RESPONSIVENESS: Always code layouts using fluid percentages (e.g. width: 100%), viewport units (vw, vh), flexbox, or CSS grid with auto-fit and fractional units (fr) instead of fixed pixel widths (like width: 800px). Ensure designs scale down beautifully to tablet and smartphone displays without horizontal scrolling.
"""

# Premium mock templates to run offline
MOCK_TEMPLATES = {
    "dashboard": {
        "type": "html",
        "explanation": "Voici un tableau de bord analytique moderne avec des graphiques interactifs (via Chart.js), un thème sombre type Glassmorphism, et des effets de survol fluides.",
        "code": """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sleek Analytics Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: rgba(20, 26, 45, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-primary: #6366f1;
            --accent-secondary: #d946ef;
            --accent-success: #10b981;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Outfit', sans-serif;
            transition: all 0.3s ease;
        }

        body {
            background: radial-gradient(circle at top right, #1e1b4b, var(--bg-color));
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            padding: 24px;
            overflow-x: hidden;
        }

        .container {
            width: 100%;
            max-width: 1400px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 240px 1fr;
            gap: 24px;
        }

        /* Sidebar Glassmorphism */
        sidebar {
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }

        .logo {
            font-size: 1.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: 1px;
        }

        .menu {
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .menu-item {
            padding: 12px 16px;
            border-radius: 12px;
            color: var(--text-secondary);
            cursor: pointer;
            font-weight: 500;
        }

        .menu-item:hover, .menu-item.active {
            background: rgba(99, 102, 241, 0.15);
            color: var(--text-primary);
            border-left: 4px solid var(--accent-primary);
            padding-left: 20px;
        }

        /* Main Content */
        main {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        h1 {
            font-size: 2rem;
            font-weight: 600;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
        }

        .kpi-card {
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            position: relative;
            overflow: hidden;
        }

        .kpi-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary));
            opacity: 0;
        }

        .kpi-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.3);
            border-color: rgba(99, 102, 241, 0.3);
        }

        .kpi-card:hover::before {
            opacity: 1;
        }

        .kpi-label {
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-bottom: 8px;
        }

        .kpi-value {
            font-size: 1.8rem;
            font-weight: 700;
            margin-bottom: 8px;
        }

        .kpi-change {
            font-size: 0.85rem;
            color: var(--accent-success);
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .kpi-change.down {
            color: #ef4444;
        }

        /* Charts Section */
        .chart-section {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
        }

        .chart-card {
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 24px;
        }

        .chart-header {
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .chart-title {
            font-size: 1.1rem;
            font-weight: 600;
        }

        /* Responsive Media Queries */
        @media (max-width: 900px) {
            .container {
                grid-template-columns: 1fr;
            }
            sidebar {
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
                padding: 16px;
            }
            .menu {
                flex-direction: row;
                gap: 12px;
            }
            .chart-section {
                grid-template-columns: 1fr;
            }
        }
        @media (max-width: 600px) {
            sidebar {
                flex-direction: column;
                gap: 16px;
            }
            .menu {
                flex-wrap: wrap;
                justify-content: center;
            }
            body {
                padding: 12px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <sidebar>
            <div class="logo">PyDesign OS</div>
            <ul class="menu">
                <li class="menu-item active">Dashboard</li>
                <li class="menu-item">Analyses</li>
                <li class="menu-item">Projets</li>
                <li class="menu-item">Configuration</li>
            </ul>
        </sidebar>
        
        <main>
            <header>
                <div>
                    <h1>Aperçu Analytique</h1>
                    <p style="color: var(--text-secondary); margin-top: 4px;">Données en temps réel de votre application</p>
                </div>
                <div class="user-pill">Admin Mode</div>
            </header>

            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Utilisateurs Actifs</div>
                    <div class="kpi-value">12,842</div>
                    <div class="kpi-change">▲ +12.4% cette semaine</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Revenus Mensuels</div>
                    <div class="kpi-value">€45,210</div>
                    <div class="kpi-change">▲ +8.1% vs mois dernier</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Temps de Réponse</div>
                    <div class="kpi-value">84ms</div>
                    <div class="kpi-change down">▼ -2.4% (amélioration)</div>
                </div>
            </div>

            <div class="chart-section">
                <div class="chart-card">
                    <div class="chart-header">
                        <span class="chart-title">Croissance des utilisateurs</span>
                    </div>
                    <canvas id="lineChart" height="180"></canvas>
                </div>
                <div class="chart-card">
                    <div class="chart-header">
                        <span class="chart-title">Canaux d'acquisition</span>
                    </div>
                    <canvas id="doughnutChart" height="180"></canvas>
                </div>
            </div>
        </main>
    </div>

    <script>
        // Line Chart Initialization
        const ctxLine = document.getElementById('lineChart').getContext('2d');
        new Chart(ctxLine, {
            type: 'line',
            data: {
                labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
                datasets: [{
                    label: 'Utilisateurs',
                    data: [4000, 5500, 7000, 6500, 9000, 12842],
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
                    y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } }
                }
            }
        });

        // Doughnut Chart Initialization
        const ctxDoughnut = document.getElementById('doughnutChart').getContext('2d');
        new Chart(ctxDoughnut, {
            type: 'doughnut',
            data: {
                labels: ['Recherche', 'Direct', 'Réseaux', 'Parrainage'],
                datasets: [{
                    data: [45, 25, 20, 10],
                    backgroundColor: ['#6366f1', '#d946ef', '#10b981', '#f59e0b'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: '#94a3b8', font: { family: 'Outfit' } }
                    }
                }
            }
        });
    </script>
</body>
</html>"""
    },
    "plot": {
        "type": "python",
        "explanation": "Voici un script Python qui génère des courbes de sinus et de cosinus bruitées avec un style sombre moderne (grille indigo/slate) et calcule des moyennes mobiles via Pandas. Cliquez sur l'onglet **Preview** pour voir le graphique généré !",
        "code": """import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Génération de données temporelles
np.random.seed(42)
x = np.linspace(0, 10, 100)
y_sin = np.sin(x) + np.random.normal(0, 0.1, 100)
y_cos = np.cos(x) + np.random.normal(0, 0.1, 100)

df = pd.DataFrame({
    'x': x,
    'Sinus': y_sin,
    'Cosinus': y_cos
})

# Calcul d'une moyenne mobile
df['Sinus_smooth'] = df['Sinus'].rolling(window=5, min_periods=1).mean()

# Configuration du style sombre pour le graphique
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

# Tracé des courbes avec des couleurs harmonieuses
ax.plot(df['x'], df['Sinus'], label='Sinus bruité', color='#6366f1', alpha=0.4, linestyle='--')
ax.plot(df['x'], df['Sinus_smooth'], label='Moyenne mobile (5)', color='#6366f1', linewidth=2.5)
ax.plot(df['x'], df['Cosinus'], label='Cosinus bruité', color='#d946ef', alpha=0.7, linewidth=1.5)

# Styling des axes et légendes
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#334155')
ax.spines['bottom'].set_color('#334155')

ax.xaxis.grid(True, linestyle=':', alpha=0.3, color='#475569')
ax.yaxis.grid(True, linestyle=':', alpha=0.3, color='#475569')

ax.set_title("Analyse de signaux avec moyennes mobiles", fontsize=14, pad=15, weight='bold', color='#f8fafc')
ax.set_xlabel("Temps (s)", color='#94a3b8')
ax.set_ylabel("Amplitude", color='#94a3b8')

# Custom legend
ax.legend(facecolor='#0f172a', edgecolor='#1e293b', labelcolor='#e2e8f0')

print("Analyse de signal terminée.")
print(f"Moyenne du sinus : {df['Sinus'].mean():.4f}")
print(f"Moyenne du cosinus : {df['Cosinus'].mean():.4f}")

plt.show()
"""
    },
    "simulation": {
        "type": "python",
        "explanation": "Voici une simulation physique d'un attracteur chaotique de Lorenz (théorie du chaos) tracée en 3D avec Matplotlib. Le script résout les équations différentielles et les affiche sur un graphique tridimensionnel.",
        "code": """import numpy as np
import matplotlib.pyplot as plt

def lorenz(x, y, z, s=10, r=28, b=2.667):
    x_dot = s*(y - x)
    y_dot = r*x - y - x*z
    z_dot = x*y - b*z
    return x_dot, y_dot, z_dot

dt = 0.01
num_steps = 2500

xs = np.empty(num_steps + 1)
ys = np.empty(num_steps + 1)
zs = np.empty(num_steps + 1)

xs[0], ys[0], zs[0] = (0., 1., 1.05)

for i in range(num_steps):
    x_dot, y_dot, z_dot = lorenz(xs[i], ys[i], zs[i])
    xs[i + 1] = xs[i] + (x_dot * dt)
    ys[i + 1] = ys[i] + (y_dot * dt)
    zs[i + 1] = zs[i] + (z_dot * dt)

# Tracé 3D
plt.style.use('dark_background')
fig = plt.figure(figsize=(10, 7), dpi=150)
ax = fig.add_subplot(projection='3d')

# Couleur dégradée le long de la trajectoire
colors = plt.cm.plasma(np.linspace(0, 1, num_steps))

for i in range(num_steps):
    ax.plot(xs[i:i+2], ys[i:i+2], zs[i:i+2], color=colors[i], alpha=0.8, linewidth=0.7)

ax.set_title("Attracteur chaotique de Lorenz (Simulation 3D)", fontsize=14, pad=15, weight='bold', color='#f8fafc')
ax.axis('off') # masquer les axes pour un rendu artistique pur

print("Attracteur de Lorenz simulé avec succès.")
print(f"Coordonnées finales : ({xs[-1]:.2f}, {ys[-1]:.2f}, {zs[-1]:.2f})")

plt.show()
"""
    },
    "form": {
        "type": "html",
        "explanation": "Voici un formulaire de contact/feedback moderne avec un effet de flou d'arrière-plan (glassmorphism), des micro-animations sur les boutons de validation, et des dégradés subtils.",
        "code": """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Feedback Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: #f8fafc;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 20px;
        }
        .form-card {
            background: rgba(30, 41, 59, 0.4);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            padding: 40px;
            width: 100%;
            max-width: 480px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            text-align: center;
            transition: transform 0.3s ease;
        }
        .form-card:hover {
            transform: translateY(-2px);
        }
        h2 {
            font-size: 2rem;
            margin-bottom: 8px;
            background: linear-gradient(135deg, #6366f1, #d946ef);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        p {
            color: #94a3b8;
            margin-bottom: 32px;
            font-size: 0.95rem;
        }
        .input-group {
            text-align: left;
            margin-bottom: 20px;
        }
        label {
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            color: #cbd5e1;
            margin-bottom: 8px;
            letter-spacing: 0.5px;
        }
        input, textarea {
            width: 100%;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 12px 16px;
            color: white;
            font-size: 0.95rem;
            box-sizing: border-box;
            transition: all 0.2s;
        }
        input:focus, textarea:focus {
            outline: none;
            border-color: #6366f1;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }
        button {
            width: 100%;
            background: linear-gradient(135deg, #6366f1 0%, #d946ef 100%);
            color: white;
            border: none;
            padding: 14px;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            margin-top: 10px;
            transition: all 0.2s;
        }
        button:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
        }
        
        /* Responsive Media Query */
        @media (max-width: 480px) {
            .form-card {
                padding: 24px 16px;
                border-radius: 16px;
            }
            body {
                padding: 12px;
            }
        }
    </style>
</head>
<body>
    <div class="form-card">
        <h2>Nous Contacter</h2>
        <p>Envoyez-nous vos retours sur l'application PyDesign.</p>
        <form id="contactForm" onsubmit="event.preventDefault(); document.getElementById('success').style.display='block';">
            <div class="input-group">
                <label>NOM COMPLET</label>
                <input type="text" placeholder="Alex Mercer" required>
            </div>
            <div class="input-group">
                <label>ADRESSE E-MAIL</label>
                <input type="email" placeholder="alex@example.com" required>
            </div>
            <div class="input-group">
                <label>MESSAGE</label>
                <textarea rows="4" placeholder="Votre message..." required></textarea>
            </div>
            <button type="submit">Envoyer le message</button>
            <div id="success" class="success-msg">✓ Message envoyé avec succès !</div>
        </form>
    </div>
</body>
</html>"""
    },
    "presentation": {
        "type": "python",
        "explanation": "Voici un script Python qui génère une présentation PowerPoint (.pptx) moderne et épurée (diapositive de titre, objectifs, et conclusion) en utilisant la bibliothèque python-pptx. Cliquez sur l'onglet **Preview** ou lancez le script pour générer et télécharger le fichier !",
        "code": """import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

# Initialisation de la présentation
prs = Presentation()
prs.slide_width = Inches(13.33)  # Format 16:9
prs.slide_height = Inches(7.5)

# Palette de couleurs "Sleek Dark"
COLOR_BG = RGBColor(11, 15, 25)       # Slate très sombre #0b0f19
COLOR_PRIMARY = RGBColor(99, 102, 241) # Indigo #6366f1
COLOR_TEXT = RGBColor(248, 250, 252)   # Blanc cassé #f8fafc
COLOR_MUTED = RGBColor(148, 163, 184)  # Slate secondaire #94a3b8

def set_slide_background(slide, color):
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color

# --- Slide 1: Titre ---
slide_layout = prs.slide_layouts[6] # Mise en page vierge
slide1 = prs.slides.add_slide(slide_layout)
set_slide_background(slide1, COLOR_BG)

# Titre principal
title_box = slide1.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.33), Inches(3.0))
tf = title_box.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "ATHENADESIGN STUDIO"
p.font.name = 'Arial'
p.font.size = Pt(54)
p.font.bold = True
p.font.color.rgb = COLOR_PRIMARY
p.space_after = Pt(14)

p2 = tf.add_paragraph()
p2.text = "Génération automatisée de présentations PowerPoint professionnelles"
p2.font.name = 'Arial'
p2.font.size = Pt(22)
p2.font.color.rgb = COLOR_TEXT

# --- Slide 2: Contenu / Objectifs ---
slide2 = prs.slides.add_slide(slide_layout)
set_slide_background(slide2, COLOR_BG)

# Titre de diapositive
title_box = slide2.shapes.add_textbox(Inches(1.0), Inches(0.8), Inches(11.33), Inches(1.0))
tf = title_box.text_frame
p = tf.paragraphs[0]
p.text = "Fonctionnalités Clés"
p.font.name = 'Arial'
p.font.size = Pt(36)
p.font.bold = True
p.font.color.rgb = COLOR_PRIMARY

# Zone de texte principale (points clés)
content_box = slide2.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.33), Inches(4.5))
tf_content = content_box.text_frame
tf_content.word_wrap = True

points = [
    ("Orchestration Multi-Agent", "Routage sémantique intelligent et collaboration organique entre agents spécialisés."),
    ("Visualisation interactive (AthenaDesign)", "Cockpit de télémétrie, bureau virtuel en 3D isométrique et annotations graphiques."),
    ("Génération PPTX Native", "Création automatique de livrables PowerPoint de qualité professionnelle directement depuis l'interface.")
]

for title, desc in points:
    p_title = tf_content.add_paragraph() if tf_content.text else tf_content.paragraphs[0]
    p_title.text = f"• {title}"
    p_title.font.name = 'Arial'
    p_title.font.size = Pt(22)
    p_title.font.bold = True
    p_title.font.color.rgb = COLOR_TEXT
    p_title.space_after = Pt(4)
    
    p_desc = tf_content.add_paragraph()
    p_desc.text = f"  {desc}"
    p_desc.font.name = 'Arial'
    p_desc.font.size = Pt(16)
    p_desc.font.color.rgb = COLOR_MUTED
    p_desc.space_after = Pt(20)

# --- Slide 3: Conclusion ---
slide3 = prs.slides.add_slide(slide_layout)
set_slide_background(slide3, COLOR_BG)

title_box = slide3.shapes.add_textbox(Inches(1.0), Inches(2.5), Inches(11.33), Inches(3.0))
tf = title_box.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "Prêt à démarrer ?"
p.font.name = 'Arial'
p.font.size = Pt(44)
p.font.bold = True
p.font.color.rgb = COLOR_PRIMARY
p.space_after = Pt(10)

p2 = tf.add_paragraph()
p2.text = "Votre présentation est générée dans le dossier de sandbox de votre projet."
p2.font.name = 'Arial'
p2.font.size = Pt(18)
p2.font.color.rgb = COLOR_TEXT

# Sauvegarde de la présentation
output_filename = "presentation_athena.pptx"
prs.save(output_filename)
print(f"Présentation PPTX générée avec succès : {output_filename}")
"""
    }
}

def parse_artifact_response(text: str) -> dict:
    """Helper to extract artifact properties from XML tags returned by LLM."""
    artifact_type = "html"
    explanation = "Code généré par PyDesign."
    code = ""
    
    # Try parsing artifact_type
    type_match = re.search(r"<artifact_type>(.*?)</artifact_type>", text, re.DOTALL)
    if type_match:
        artifact_type = type_match.group(1).strip().lower()
        
    # Try parsing explanation
    exp_match = re.search(r"<artifact_explanation>(.*?)</artifact_explanation>", text, re.DOTALL)
    if exp_match:
        explanation = exp_match.group(1).strip()
        
    # Try parsing code block
    code_match = re.search(r"<artifact_code>(.*?)</artifact_code>", text, re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()
    else:
        # Fallback: find standard markdown code blocks
        md_code_blocks = re.findall(r"```(?:html|python|css|javascript|py)?\n(.*?)```", text, re.DOTALL)
        if md_code_blocks:
            code = md_code_blocks[0].strip()
        else:
            code = text # Last fallback
            
    # Clean code: if LLM put code block around it anyway, strip them
    if code.startswith("```"):
        code = re.sub(r"^```[a-zA-Z]*\n", "", code)
        code = re.sub(r"\n```$", "", code)
        
    return {
        "type": "python" if "python" in artifact_type else "html",
        "explanation": explanation,
        "code": code
    }

def _athena_default_model() -> str:
    """Modèle LLM par défaut d'AthenaDesign : ATHENADESIGN_MODEL si défini, sinon le modèle
    de l'orchestrateur (config Athena), sinon un repli raisonnable."""
    import os
    forced = os.getenv("ATHENADESIGN_MODEL", "").strip()
    if forced:
        return forced
    try:
        from core.state import swarm as _sw
        orch = getattr(_sw, "orchestrator_name", "Athena")
        agent = _sw.agents.get(orch)
        if agent and getattr(agent, "model", None):
            return agent.model
    except Exception:
        pass
    return os.getenv("DEFAULT_MODEL", "").strip() or "qwen3"


def _generate_via_athena(prompt: str, history: list, model_name: str = "") -> dict:
    """Génère via l'INFRA LLM d'Athena (swarm._complete) : endpoint/clés/fallback configurés
    dans Athena (et par-utilisateur), pas un chemin LLM séparé. Synchrone (à appeler en thread)."""
    from core.state import swarm as _sw
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in (history or []):
        role = m.get("role")
        if role in ("user", "assistant") and m.get("content"):
            messages.append({"role": role, "content": m["content"]})
    messages.append({"role": "user", "content": prompt})
    model = (model_name or "").strip() or _athena_default_model()
    resp = _sw._complete(model, messages, tools_schema=None, allow_continuation=True, allow_fallback=True)
    text = (resp.choices[0].message.content or "")
    return parse_artifact_response(text)


async def generate_design(prompt: str, history: list, provider: str = "athena",
                          api_key: str = "", model_name: str = "") -> dict:
    """Routeur LLM. Par DÉFAUT (provider 'athena' ou non précisé), passe par l'infra LLM
    d'Athena (clés/endpoint/fallback configurés). 'mock' → templates hors-ligne. Les providers
    externes explicites (gemini/anthropic/openai) restent possibles si une clé est fournie."""
    import asyncio

    if provider == "mock":
        prompt_lower = prompt.lower()
        if "simulation" in prompt_lower or "chaos" in prompt_lower or "lorenz" in prompt_lower:
            return MOCK_TEMPLATES["simulation"]
        elif "plot" in prompt_lower or "graph" in prompt_lower or "sinus" in prompt_lower or "pandas" in prompt_lower:
            return MOCK_TEMPLATES["plot"]
        elif "form" in prompt_lower or "contact" in prompt_lower or "feedback" in prompt_lower:
            return MOCK_TEMPLATES["form"]
        elif "powerpoint" in prompt_lower or "presentation" in prompt_lower or "pptx" in prompt_lower or "slide" in prompt_lower:
            return MOCK_TEMPLATES["presentation"]
        else:
            # Default to dashboard template
            return MOCK_TEMPLATES["dashboard"]

    # Par DÉFAUT : infra LLM d'Athena (swarm._complete) — endpoint/clés/fallback configurés
    # dans Athena. On ne tombe sur un provider EXTERNE que s'il est explicitement demandé
    # ET qu'une clé est fournie par le front.
    if provider not in ("gemini", "anthropic", "openai") or not api_key:
        try:
            return await asyncio.to_thread(_generate_via_athena, prompt, history, model_name)
        except Exception as e:
            return {"type": "html",
                    "explanation": f"⚠️ Erreur de génération via l'API d'Athena : {e}",
                    "code": ""}

    # Real LLM API calls (providers externes explicites avec clé fournie)
    headers = {}
    payload = {}
    url = ""
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            
            if provider == "gemini":
                # Using Gemini API (Google AI Studio model, e.g. gemini-2.5-flash)
                # Google standard endpoint: /v1beta/models/{model}:generateContent
                model = model_name or "gemini-2.5-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                
                # Format conversation history
                contents = []
                # System prompt as systemInstruction if supported, or prepended to the first message
                # For simplicity, we can pass systemInstruction inside systemInstruction parameter
                
                for msg in history:
                    contents.append({
                        "role": "user" if msg["role"] == "user" else "model",
                        "parts": [{"text": msg["content"]}]
                    })
                
                # Add current user prompt
                contents.append({
                    "role": "user",
                    "parts": [{"text": prompt}]
                })
                
                payload = {
                    "contents": contents,
                    "systemInstruction": {
                        "parts": [{"text": SYSTEM_PROMPT}]
                    },
                    "generationConfig": {
                        "temperature": 0.2
                    }
                }
                
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                return parse_artifact_response(text_out)
                
            elif provider == "anthropic":
                # Using Anthropic API
                model = model_name or "claude-3-5-sonnet-latest"
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                
                # Format conversation history
                messages = []
                for msg in history:
                    if msg["role"] in ["user", "assistant"]:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                messages.append({
                    "role": "user",
                    "content": prompt
                })
                
                payload = {
                    "model": model,
                    "max_tokens": 4000,
                    "system": SYSTEM_PROMPT,
                    "messages": messages,
                    "temperature": 0.2
                }
                
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                
                text_out = data["content"][0]["text"]
                return parse_artifact_response(text_out)
                
            elif provider == "openai":
                # Using OpenAI API
                model = model_name or "gpt-4o-mini"
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                for msg in history:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
                messages.append({
                    "role": "user",
                    "content": prompt
                })
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2
                }
                
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                
                text_out = data["choices"][0]["message"]["content"]
                return parse_artifact_response(text_out)
                
            else:
                raise ValueError(f"Provider inconnu : {provider}")
                
    except Exception as e:
        # Fallback to Mock template on network/API failure so the user isn't stuck
        fallback = MOCK_TEMPLATES["dashboard"]
        fallback["explanation"] = f"⚠️ [Erreur API : {str(e)}]\nUne erreur est survenue lors de l'appel à {provider.capitalize()}. Chargement du modèle de démonstration local à la place."
        return fallback
