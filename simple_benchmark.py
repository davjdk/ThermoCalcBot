"""
Simple performance benchmark for Stage 8 migration testing.
Tests system performance with 10 compounds as specified in the requirements.
"""

import asyncio
import time
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from main import create_orchestrator


async def benchmark():
    """Performance test for 10 compounds reaction."""
    print("Performance Benchmark - Stage 8")
    print("=" * 50)

    # Create orchestrator
    db_path = Path(__file__).parent / "data" / "thermo_data.db"
    orchestrator = create_orchestrator(str(db_path))

    # Test: reaction with 10 compounds (maximum supported)
    query = "Complex reaction with 10 compounds at 500-800K: H2 + O2 + N2 + CO2 + H2O + CO + NH3 + CH4 + SO2 + Cl2 -> Products"

    print(f"Query: {query}")
    print("Processing...")

    start_time = time.time()

    try:
        response = await orchestrator.process_query(query)
        elapsed = time.time() - start_time

        print(f"SUCCESS: Processing completed!")
        print(f"Time: {elapsed:.2f} seconds")

        if elapsed < 5.0:
            print("PERFORMANCE TARGET MET (< 5 seconds)")
        else:
            print("PERFORMANCE TARGET EXCEEDED (> 5 seconds)")

        print(f"Response length: {len(response)} characters")

        # Show first few lines of response
        lines = response.split('\n')[:5]
        print("\nResponse preview:")
        print("-" * 30)
        for line in lines:
            if line.strip():
                print(line)

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"ERROR after {elapsed:.2f} seconds: {e}")

    finally:
        await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(benchmark())