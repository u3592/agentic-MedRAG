import json

data = {
  "hypotheses": [
    {
      "premises": [
        {"text": "Patient presents sign F, G and symptoms H.", "source": "context"},
        {"text": "Signs F, G are strongly associated with condition J", "source": "medical knowledge"}
      ],
      "conclusion": "Patient has condition J."
    },
    {
      "premises": [
        {"text": "Patient has condition J.", "source": "prior conclusion"},
        {"text": "Condition J is commonly caused by disease K.", "source": "medical knowledge"}
      ],
      "conclusion": "Patient may have disease K."
    },
    {
      "premises": [
        {"text": "Patient may have disease K.", "source": "prior conclusion"},
        {"text": "Condition J is commonly caused by disease K.", "source": "medical knowledge"}
      ],
      "conclusion": "Patient has disease K."
    },
    {
      "premises": [
        {"text": "Patient has disease K.", "source": "prior conclusion"},
        {"text": "Disease K has subtype L and subtype M.", "source": "medical knowledge"},
        {"text": "Symptom H is strongly associated with subtype M", "source": "medical knowledge"}
      ],
      "conclusion": "Patient has disease K subtype M."
    },
    {
      "premises": [
        {"text": "Patient has disease K subtype M.", "source": "prior conclusion"},
        {"text": "Option states Disease K Type M", "source": "context"}
      ],
      "conclusion": "Option is correct."
    }
  ]
}

# Convert to JSON string
json_string = json.dumps(data, indent=2)
print(json_string)