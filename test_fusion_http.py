#!/usr/bin/env python3
"""
Test script for Fusion HTTP Server
Run this after starting the Fusion HTTP server to verify it's working
"""

import requests
import json
import time

FUSION_URL = "http://localhost:8080"

def test_connection():
    """Test if Fusion HTTP server is running"""
    print("Testing connection to Fusion HTTP server...")
    try:
        response = requests.post(
            FUSION_URL,
            json={"tool": "sketchRectangle", "params": {"length": 1, "width": 1}},
            timeout=5
        )
        response.raise_for_status()
        print("✅ Connection successful!")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return True
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Fusion server.")
        print("Please ensure:")
        print("  1. Fusion 360 is running")
        print("  2. The fusion_http_server.py script is running in Fusion")
        print("  3. You see the message 'Fusion HTTP Server started on port 8080!'")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_rounded_box():
    """Test creating a complete rounded box"""
    print("\n" + "="*60)
    print("Testing complete workflow: Rectangle → Extrude → Fillet")
    print("="*60)

    # Step 1: Create rectangle
    print("\n[1/3] Creating 10x10 cm rectangle...")
    try:
        response = requests.post(
            FUSION_URL,
            json={"tool": "sketchRectangle", "params": {"length": 10, "width": 10}},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") == "success":
            print("✅ Rectangle created successfully")
        else:
            print(f"❌ Failed: {result.get('message')}")
            return False
        time.sleep(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # Step 2: Extrude
    print("\n[2/3] Extruding 5 cm...")
    try:
        response = requests.post(
            FUSION_URL,
            json={"tool": "extrude", "params": {"distance": 5}},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") == "success":
            print("✅ Extrusion created successfully")
        else:
            print(f"❌ Failed: {result.get('message')}")
            return False
        time.sleep(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # Step 3: Fillet
    print("\n[3/3] Filleting edges with 1 cm radius...")
    try:
        response = requests.post(
            FUSION_URL,
            json={"tool": "fillet", "params": {"radius": 1}},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") == "success":
            print("✅ Fillet applied successfully")
        else:
            print(f"❌ Failed: {result.get('message')}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    print("\n" + "="*60)
    print("✅ All tests passed! Check Fusion 360 to see the rounded box.")
    print("="*60)
    return True

if __name__ == "__main__":
    print("Fusion HTTP Server Test Script")
    print("="*60)

    if test_connection():
        print("\nServer is running! Now testing the complete workflow...")
        print("Note: This will create geometry in your active Fusion design.")
        print("Make sure you have a fresh design open (File → New Design)")

        input("\nPress Enter to continue...")
        test_rounded_box()
    else:
        print("\nPlease start the Fusion HTTP server and try again.")
