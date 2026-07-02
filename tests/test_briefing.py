import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["STATE_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name


def test_get_daily_briefing():
    from tools.briefing_tools import get_daily_briefing
    import tools.list_tools as L
    
    # Pre-populate lists so get_daily_briefing has tasks and courses
    L.add_list_item("taches", "Acheter du pain")
    L.add_list_item("courses", "Lait")

    # Mock get_weather (Open-Meteo) pour éviter tout appel réseau : le briefing prend la
    # 1ʳᵉ ligne (conditions actuelles) + la 1ʳᵉ ligne de prévision « - … ».
    weather = ("Météo actuelle à Strasbourg : Soleil: 22°C (ressenti 21°C).\n\nPrévisions :\n"
               "- jeu. : ensoleillé, 15/24°C")
    with patch("tools.basic_tools.get_weather", return_value=weather):
        briefing = get_daily_briefing(city="Strasbourg")
        
    assert "☀️ **BRIEFING DU JOUR" in briefing
    assert "Strasbourg" in briefing
    assert "Soleil: 22°C" in briefing
    assert "Acheter du pain" in briefing
    assert "Lait" in briefing
    
    print("OK test_get_daily_briefing")


if __name__ == "__main__":
    test_get_daily_briefing()
    print("\nTous les tests de briefing passent.")
