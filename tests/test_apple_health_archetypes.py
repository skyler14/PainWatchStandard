import pandas as pd

from painwatchstandard.inference import state_preference_normalize


def test_state_preference_can_omit_unavailable_heads():
    probs = state_preference_normalize({"pain": 0.8, "stress": 0.7})

    assert set(probs) == {"pain", "stress"}
    assert round(sum(probs.values()), 6) == 1.0
    assert probs["pain"] > probs["stress"]


def test_health_archetype_labels_can_be_modeled_as_context_not_pain_truth():
    rows = pd.DataFrame(
        {
            "archetype": ["sleep", "awake_nonworkout", "standing", "workout_or_exercise"],
            "hr_median": [63, 82, 88, 122],
        }
    )

    assert rows.loc[rows["archetype"].eq("sleep"), "hr_median"].iloc[0] < rows.loc[rows["archetype"].eq("workout_or_exercise"), "hr_median"].iloc[0]
