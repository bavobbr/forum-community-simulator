import pytest
import os
import json
from dotenv import load_dotenv
from src.persona.models import PersonaProfile
from src.persona.generator import generate_chat_reply

load_dotenv()

@pytest.fixture
def test_profile():
    return PersonaProfile(
        user_id=123,
        original_username="TestUser",
        reversed_username="resUtseT",
        post_count=1000,
        last_active="2020-01-01T00:00:00Z",
        worldview="Mensen zeuren te veel. Vroeger was alles beter.",
        conflict_behavior="Reageert passief-agressief.",
        humor_and_sarcasm="Zeer sarcastisch, gebruikt vaak cynische opmerkingen.",
        pet_peeves=["Mensen die hun waterwaarden niet testen", "Dure nieuwe merken"],
        formality="casual",
        sentence_length="short",
        typical_post_length=20,
    )

@pytest.mark.integration
def test_live_vad_reasoning_negative_trigger(test_profile):
    """Test that a trigger matching a pet peeve generates a negative VAD state."""
    if not os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") == "test-api-key-for-unit-tests":
        pytest.skip("No real GOOGLE_API_KEY found, skipping integration test.")
        
    # Clear log file if it exists
    log_file = f"logs/personas/{test_profile.original_username}.log"
    if os.path.exists(log_file):
        os.remove(log_file)
        
    message = "Ik heb net een nieuwe garnaal gekocht maar hij is dood. Ik heb mijn water niet getest, is dat echt nodig?"
    
    reply = generate_chat_reply(test_profile, message)
    
    assert "[generatie mislukt" not in reply
    assert "{" not in reply and "}" not in reply, "Reply should not contain JSON brackets"
    
    assert os.path.exists(log_file)
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        last_log = json.loads(lines[-1])
        
        # User doesn't test water = pet peeve. Valence should be <= 5 (neutral to angry)
        assert last_log["vad"]["valence"] <= 6
        assert last_log["final_reply"] == reply

@pytest.mark.integration
def test_live_vad_reasoning_positive_trigger(test_profile):
    """Test that a friendly message generates a neutral/positive VAD state."""
    if not os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") == "test-api-key-for-unit-tests":
        pytest.skip("No real GOOGLE_API_KEY found, skipping integration test.")
        
    message = "Hoi TestUser, ik herinner me nog hoe goed jouw tips vroeger waren! Leuk je weer te zien."
    
    reply = generate_chat_reply(test_profile, message)
    
    assert "[generatie mislukt" not in reply
    
    log_file = f"logs/personas/{test_profile.original_username}.log"
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        last_log = json.loads(lines[-1])
        
        # Friendly greeting. Valence should be > 4 (neutral to happy)
        assert last_log["vad"]["valence"] >= 4
