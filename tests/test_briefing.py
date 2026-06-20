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

    # Mock requests.get to prevent real network requests to wttr.in
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "Soleil: 22°C"
    
    with patch("requests.get", return_value=mock_resp):
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
