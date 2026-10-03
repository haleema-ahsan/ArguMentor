# ⚔️ ArguMentor - Adaptive AI Debate Simulator

ArguMentor is a Streamlit app where you debate an AI opponent. You pick a topic
and a side (Support or Oppose), the AI takes the opposite side, and it adapts
its counterarguments to what you actually write. At the end you get ONE final
performance report on how well you debated.

The report judges your **debating performance**, never which political, social,
or moral side is correct.

## How it works

```
Topic Analyzer
      ↓
AI Opening Argument
      ↓
User Argument → Adaptive Debate Agent → AI Counterargument
      ↓
User Argument → Adaptive Debate Agent → AI Counterargument
      ↓
   ... (3, 5, or 7 rounds)
      ↓
Final Assessment (one call)
      ↓
Performance Feedback
```

- **Topic Analyzer** - accepts broad or open-ended topics (for example
  "Is all fair in love and war?") and only rejects meaningless input.
- **Debate Agent** - reads your latest argument plus recent history, finds the
  weakest point, and responds directly to it. It does not invent sources.
- **Final Assessment** - one call at the end: scores, strengths, weaknesses,
  strongest and weakest argument, and improvement suggestions.

There is no per-round evaluator and no web search, which keeps Groq token usage low.

## Groq calls per debate

Topic analysis (1) + opening (1) + counterarguments (rounds - 1) + final assessment (1)

| Rounds | Groq calls |
|---|---|
| 3 | 5 |
| 5 | 7 |
| 7 | 9 |

On the last round the debate ends right after your argument, so the AI does not
write a reply that would never be shown.

## Project files

```
ArguMentor/
├── app.py            # Streamlit UI and page navigation
├── workflow.py       # Groq calls: topic analysis, debate agent, final assessment
├── prompts.py        # System prompts
├── requirements.txt
├── README.md
└── .gitignore
```

## Run locally

1. Install Python 3.10 or newer.
2. Install the requirements:
   ```
   pip install -r requirements.txt
   ```
3. Create the file `.streamlit/secrets.toml` in the project folder:
   ```toml
   GROQ_API_KEY = "gsk_your_key_here"
   ```
4. Start the app:
   ```
   streamlit run app.py
   ```

## Deploy on Streamlit Community Cloud

1. Push this repository to GitHub (the `.gitignore` keeps your secrets out).
2. On [share.streamlit.io](https://share.streamlit.io), create a new app from the repo and choose `app.py`.
3. Open **Settings → Secrets** and add:
   ```toml
   GROQ_API_KEY = "gsk_your_key_here"
   ```
4. Save and reboot the app.

Get a key at [console.groq.com](https://console.groq.com) under **API Keys**.
Never put the key in the code or commit it to GitHub.

## Rate limits

Groq limits tokens per minute and per day for each organization and model. If you
see "Groq's token limit has been reached", wait before starting another debate.
The app never retries automatically, because retries would use more quota.
The message also shows Groq's original error so you can see which limit was hit.

## Tuning

At the top of `workflow.py` you can change the model name, `RECENT_ROUNDS`
(how many rounds the AI sees in full), and `LOW_REASONING`. The `max_tokens`
value in each call controls its maximum output size.
