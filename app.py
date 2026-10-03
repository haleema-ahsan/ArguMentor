import streamlit as st
from workflow import (
    initialize_debate,
    submit_user_argument,
    generate_final_assessment,
    validate_api_key,
    friendly_error,
)

st.set_page_config(
    page_title="ArguMentor",
    page_icon="⚔️",
    layout="wide",
)

# -----------------------------
# Simple styling
# -----------------------------
st.markdown(
    """
    <style>
    .block-container {max-width: 1100px; padding-top: 2rem;}
    .hero {
        padding: 1.5rem;
        border-radius: 16px;
        background: linear-gradient(135deg, #111827, #1f2937);
        color: white;
        margin-bottom: 1.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Session state
# -----------------------------
DEFAULTS = {
    "page": "setup",
    "topic": "",
    "topic_analysis": None,
    "user_position": None,
    "ai_position": None,
    "total_rounds": 5,
    "current_round": 0,
    "debate_history": [],
    "final_assessment": None,
    "assessment_failed": False,
    "ai_opening": "",
    "error_message": None,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset_debate():
    for key, value in DEFAULTS.items():
        st.session_state[key] = value


# -----------------------------
# Setup page
# -----------------------------
def setup_page():
    st.markdown(
        """
        <div class="hero">
            <h1>⚔️ ArguMentor</h1>
            <p style="font-size:1.1rem;">Adaptive AI Debate Simulator</p>
            <p>Choose a topic, take a position, and challenge an AI opponent that adapts to your arguments.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    topic = st.text_area(
        "Debate topic",
        placeholder="Should governments ban single-use plastics?",
        height=110,
        key="setup_topic",
    )

    col1, col2 = st.columns(2)

    with col1:
        position = st.radio(
            "Your position",
            ["Support", "Oppose"],
            horizontal=True,
        )

    with col2:
        rounds = st.selectbox(
            "Number of rounds",
            [3, 5, 7],
            index=1,
        )

    st.info(
        "The AI always takes the opposite position. "
        "The debate evaluates how well you defend your assigned side; "
        "it does not decide which social or political position is objectively correct."
    )

    if st.button("🚀 Start Debate", type="primary", use_container_width=True):
        if not topic.strip():
            st.error("Please enter a debate topic.")
            return

        if not validate_api_key():
            st.error(
                "GROQ_API_KEY is missing. Add it to Streamlit Secrets "
                "or your local .streamlit/secrets.toml file."
            )
            return

        with st.spinner("Analyzing your topic and preparing the debate..."):
            try:
                result = initialize_debate(
                    topic=topic.strip(),
                    requested_position=position,
                )

                if not result["success"]:
                    analysis = result.get("topic_analysis", {})
                    reason = analysis.get("reason", "This topic needs clarification.")
                    suggestion = analysis.get("suggested_topic", "")
                    st.error(reason)
                    if suggestion:
                        st.info(f"Suggested clearer topic: **{suggestion}**")
                    return

                st.session_state.topic = result["topic"]
                st.session_state.topic_analysis = result["topic_analysis"]
                st.session_state.user_position = result["user_position"]
                st.session_state.ai_position = result["ai_position"]
                st.session_state.total_rounds = rounds
                st.session_state.current_round = 1
                st.session_state.ai_opening = result["opening_argument"]
                st.session_state.page = "debate"
                st.session_state.error_message = None
                st.rerun()

            except Exception as exc:
                st.error(friendly_error(exc, "Could not start the debate"))


# -----------------------------
# Debate page
# -----------------------------
def debate_page():
    st.title("⚔️ Debate Arena")

    top1, top2, top3 = st.columns(3)
    top1.metric("Your position", st.session_state.user_position)
    top2.metric("AI position", st.session_state.ai_position)
    top3.metric(
        "Round",
        f"{st.session_state.current_round} / {st.session_state.total_rounds}",
    )

    st.progress(
        st.session_state.current_round / st.session_state.total_rounds,
        text=f"Round {st.session_state.current_round} of {st.session_state.total_rounds}",
    )

    with st.expander("Debate topic", expanded=True):
        st.write(st.session_state.topic)

    # Earlier rounds (just the conversation, no scores or evaluation)
    if st.session_state.debate_history:
        with st.expander("💬 Previous rounds"):
            for item in st.session_state.debate_history:
                st.markdown(f"**Round {item['round']} - AI:** {item['ai_argument']}")
                st.markdown(f"**Round {item['round']} - You:** {item['user_argument']}")
                st.divider()

    if st.session_state.current_round == 1:
        st.subheader("🤖 AI opening argument")
    else:
        st.subheader("🤖 AI counterargument")
    st.markdown(st.session_state.ai_opening)

    st.divider()

    with st.form("argument_form", clear_on_submit=True):
        user_argument = st.text_area(
            "Your response",
            placeholder="Present your argument clearly. You can make a claim, give evidence, challenge the AI, or respond to its previous point.",
            height=180,
        )
        submitted = st.form_submit_button(
            "Submit Argument",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not user_argument.strip():
            st.warning("Please enter your argument before submitting.")
            return

        with st.spinner("Reading your argument and preparing a response..."):
            try:
                result = submit_user_argument(
                    user_argument=user_argument.strip(),
                    topic=st.session_state.topic,
                    user_position=st.session_state.user_position,
                    ai_position=st.session_state.ai_position,
                    current_round=st.session_state.current_round,
                    total_rounds=st.session_state.total_rounds,
                    ai_last_argument=st.session_state.ai_opening,
                    debate_history=st.session_state.debate_history,
                )

                st.session_state.debate_history.append(
                    {
                        "round": st.session_state.current_round,
                        "ai_argument": st.session_state.ai_opening,
                        "user_argument": user_argument.strip(),
                        "ai_response": result["ai_response"],
                    }
                )

                if st.session_state.current_round >= st.session_state.total_rounds:
                    st.session_state.page = "results"
                    st.session_state.final_assessment = None
                    st.session_state.assessment_failed = False
                else:
                    st.session_state.current_round += 1
                    st.session_state.ai_opening = result["ai_response"]

                st.rerun()

            except Exception as exc:
                st.error(friendly_error(exc, "Could not process this round"))
                # The form clears itself on submit, so show the text again
                # so the user does not lose what they typed.
                st.caption("Your argument was not submitted. Copy it so you can try again:")
                st.code(user_argument, language=None)

    if st.button("↩️ End debate and start over"):
        reset_debate()
        st.rerun()


# -----------------------------
# Results page
# -----------------------------
def results_page():
    st.title("🏁 Debate Complete")

    if st.session_state.final_assessment is None:
        # If the last attempt failed, wait for the user to click "try again"
        # instead of automatically calling Groq again.
        if st.session_state.assessment_failed:
            st.error(st.session_state.error_message)
            if st.button("Try generating the assessment again", type="primary"):
                st.session_state.assessment_failed = False
                st.rerun()
            if st.button("🔄 Start a New Debate"):
                reset_debate()
                st.rerun()
            return

        with st.spinner("Generating your final performance assessment..."):
            try:
                st.session_state.final_assessment = generate_final_assessment(
                    topic=st.session_state.topic,
                    user_position=st.session_state.user_position,
                    ai_position=st.session_state.ai_position,
                    debate_history=st.session_state.debate_history,
                )
            except Exception as exc:
                st.session_state.assessment_failed = True
                st.session_state.error_message = friendly_error(
                    exc, "Could not generate the final assessment"
                )
                st.rerun()

    assessment = st.session_state.final_assessment

    st.subheader("Performance Overview")
    st.write(assessment.get("overall_performance", ""))

    st.subheader("Category Scores")
    scores = assessment.get("category_scores", {})
    cols = st.columns(6)
    score_names = [
        ("Argument Quality", "argument_quality"),
        ("Reasoning", "reasoning"),
        ("Relevance", "relevance"),
        ("Evidence", "evidence_usage"),
        ("Consistency", "consistency"),
        ("Adaptability", "adaptability"),
    ]

    for col, (label, key) in zip(cols, score_names):
        col.metric(label, scores.get(key, 0))

    left, right = st.columns(2)

    with left:
        st.subheader("Strengths")
        for item in assessment.get("strengths", []):
            st.markdown(f"- {item}")

        st.subheader("Strongest Argument")
        st.write(assessment.get("strongest_argument", ""))

    with right:
        st.subheader("Areas for Improvement")
        for item in assessment.get("weaknesses", []):
            st.markdown(f"- {item}")

        st.subheader("Weakest Argument")
        st.write(assessment.get("weakest_argument", ""))

    st.subheader("Evidence Performance")
    st.write(assessment.get("evidence_performance", ""))

    st.subheader("Adaptability")
    st.write(assessment.get("adaptability", ""))

    st.subheader("Response to Counterarguments")
    st.write(assessment.get("response_to_counterarguments", ""))

    st.subheader("Clarity")
    st.write(assessment.get("clarity", ""))

    st.subheader("Improvement Suggestions")
    for item in assessment.get("improvement_suggestions", []):
        st.markdown(f"- {item}")

    with st.expander("🔎 Debate history"):
        for item in st.session_state.debate_history:
            st.markdown(f"### Round {item['round']}")
            st.markdown(f"**AI:** {item['ai_argument']}")
            st.markdown(f"**You:** {item['user_argument']}")
            st.divider()

    if st.button("🔄 Start a New Debate", type="primary", use_container_width=True):
        reset_debate()
        st.rerun()


# -----------------------------
# Router
# -----------------------------
if st.session_state.page == "setup":
    setup_page()
elif st.session_state.page == "debate":
    debate_page()
elif st.session_state.page == "results":
    results_page()
