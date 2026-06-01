# run_app.py
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Now run streamlit
if __name__ == "__main__":
    import streamlit.web.cli as stcli
    import sys
    
    sys.argv = ["streamlit", "run", "app/ui/main.py"]
    sys.exit(stcli.main())