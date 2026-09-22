from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.optimization_strategies import generate, save


if __name__ == "__main__":
    result = generate(ROOT, "INC-002")
    print(save(ROOT, result))
