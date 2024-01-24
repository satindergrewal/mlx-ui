import time

import mlx.core as mx
import streamlit as st
from mlx_lm import load
from mlx_lm.utils import generate_step

title = "MLX Chat"
ver = "0.7.12"
debug = False

with open('mymodels.txt', 'r') as file:
    model_refs = [line.strip() for line in file.readlines() if not line.startswith('#')]

model_refs = {k.strip(): v.strip() for k, v in [line.split("|") for line in model_refs]}

st.set_page_config(
    page_title=title,
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title(title)

assistant_greeting = "How may I help you?"

model_ref = st.sidebar.selectbox("model", model_refs.keys(), format_func=lambda value: model_refs[value],
                                 help="See https://huggingface.co/mlx-community for more models. Add your favorites "
                                      "to models.txt")

system_prompt = st.sidebar.text_area("system prompt", "You are a helpful AI assistant trained on a vast amount of "
                                                      "human knowledge. Answer as concisely as possible.")

context_length = st.sidebar.number_input('context length', value=16384, min_value=100, step=100, max_value=32000,
                                         help="how many maximum words to print, roughly")

temperature = st.sidebar.slider('temperature', min_value=0., max_value=1., step=.10, value=1.0,
                                help="lower means less creative but more accurate")

st.sidebar.markdown("---")
actions = st.sidebar.columns(2)

st.sidebar.markdown("---")
st.sidebar.markdown(f"v{ver} / st {st.__version__}")

# give a bit of time for sidebar widgets to render
time.sleep(0.05)

if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": assistant_greeting}]


@st.cache_resource(show_spinner=True)
def load_model(ref):
    return load(ref)


model, tokenizer = load_model(model_ref)

stop_tokens = [0, 1, 2, 32000, 32001]
stop_tokens += tokenizer.all_special_ids
stop_tokens = sorted(set(stop_tokens))

chatml_template = (
    "{% for message in messages %}"
    "{{'<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n'}}"
    "{% endfor %}"
    "{% if add_generation_prompt %}"
    "{{ '<|im_start|>assistant\n' }}"
    "{% endif %}"
)


def generate(the_prompt, the_model):
    tokens = []
    skip = 0
    for token, _ in zip(generate_step(mx.array(tokenizer.encode(the_prompt)), the_model, temperature),
                        range(context_length)):

        if token in stop_tokens:
            break

        tokens.append(token.item())
        full_response = tokenizer.decode(tokens)

        yield full_response[skip:]
        skip = len(full_response)


def show_chat(the_prompt, previous=""):
    if debug:
        print(the_prompt)
        print("-" * 80)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        response = previous

        for chunk in generate(the_prompt, model):
            response = (response + chunk).replace('�', '')
            message_placeholder.markdown(response + "▌")

        message_placeholder.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})


def remove_last_occurrence(array, criteria_fn):
    for i in reversed(range(len(array))):
        if criteria_fn(array[i]):
            del array[i]
            break


def build_memory():
    if len(st.session_state.messages) > 2:
        return st.session_state.messages[1:-1]
    return []


def queue_chat(the_prompt, continuation=""):
    # workaround because the chat boxes are not really replaced until a rerun
    st.session_state["prompt"] = the_prompt
    st.session_state["continuation"] = continuation
    st.rerun()


if actions[0].button("😶‍🌫️ Forget", use_container_width=True,
                     help="Forget the previous conversations."):
    st.session_state.messages = [{"role": "assistant", "content": assistant_greeting}]
    if "prompt" in st.session_state and st.session_state["prompt"]:
        st.session_state["prompt"] = None
        st.session_state["continuation"] = None
    st.rerun()

if actions[1].button("🔂 Continue", use_container_width=True,
                     help="Continue the generation."):

    user_prompts = [msg["content"] for msg in st.session_state.messages if msg["role"] == "user"]

    if user_prompts:

        last_user_prompt = user_prompts[-1]

        assistant_responses = [msg["content"] for msg in st.session_state.messages
                               if msg["role"] == "assistant" and msg["content"] != assistant_greeting]
        last_assistant_response = assistant_responses[-1] if assistant_responses else ""

        # remove last line completely, so it is regenerated correctly (in case it stopped mid-word or mid-number)
        last_assistant_response_lines = last_assistant_response.split('\n')
        if len(last_assistant_response_lines) > 1:
            last_assistant_response_lines.pop()
            last_assistant_response = "\n".join(last_assistant_response_lines)

        full_prompt = tokenizer.apply_chat_template([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": last_user_prompt},
            {"role": "assistant", "content": last_assistant_response},
        ], tokenize=False, add_generation_prompt=False, chat_template=chatml_template)
        full_prompt = full_prompt.rstrip("<|im_end|>\n")

        # replace last assistant response from state, as it will be replaced with a continued one
        remove_last_occurrence(st.session_state.messages,
                               lambda msg: msg["role"] == "assistant" and msg["content"] != assistant_greeting)

        queue_chat(full_prompt, last_assistant_response)

if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})

    messages = [{"role": "system", "content": system_prompt}]
    messages += build_memory()
    messages += [{"role": "user", "content": prompt}]

    full_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                                chat_template=chatml_template)
    full_prompt = full_prompt.rstrip("\n")

    queue_chat(full_prompt)

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if "prompt" in st.session_state and st.session_state["prompt"]:
    show_chat(st.session_state["prompt"], st.session_state["continuation"])
    st.session_state["prompt"] = None
    st.session_state["continuation"] = None
