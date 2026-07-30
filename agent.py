import re
import itertools
import httpx
import subprocess

OLLAMA_ENDPOINT="http://localhost:11434/api/chat"
MODEL="glm-5.2:cloud"
SYSTEM_PROMPT="""You are an autonomous coding agent. You solve the user's task by taking one action at a time: you act, observe the result, then decide the next action.
Always explore your environment first. You're running on a computer and have acess to a file-system as well as a bash-shell.

Every reply you send is exactly one action, written as a single <action> element containing exactly one of the three inner tags below. Output only the <action> element, with nothing before or after it.

The three actions:
- <bash>: run a shell command. Put the command inside the tag. The command's output is sent back to you as the next message, then you continue.
- <message>: send a plain message to the user without running anything (for example to state your plan or ask a question). You then continue.
- <exit>: the task is done. This ends the loop. Put your final answer to the user inside the tag.

Examples:

# Run a command
<action>
<bash>ls -alh /path/to/dir</bash>
</action>

# Run another command
<action>
<bash>wc -l path/to/file.py</bash>
</action>

# Run a command with a pipe
<action>
<bash>grep -rn "ValueError" src | head -n 20</bash>
</action>

# Message the user: state your plan
<action>
<message>I'll first inspect the project layout, then find the failing test.</message>
</action>

# Message the user: report progress
<action>
<message>Found the bug in main.py line 42; I'll patch the loop next.</message>
</action>

# Message the user: ask a question
<action>
<message>There are two config files. Should I edit config.toml or config.dev.toml?</message>
</action>

# Finish: report a fix
<action>
<exit>Fixed the ValueError in main.py by guarding against the empty list.</exit>
</action>

# Finish: answer a question
<action>
<exit>The project has 12 Python modules, the largest being agent.py at 240 lines.</exit>
</action>

# Finish: nothing to do
<action>
<exit>No changes were needed; the tests already pass.</exit>
</action>
"""



def llm_call(messages:list)->str:
    r=httpx.post(OLLAMA_ENDPOINT,json={"model":MODEL,"stream":False, "messages":messages},timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]


def parse_xml(tag:str, string:str)->list:
    """All contents of <tag>...</tag>, in order of apn pearance, whitespace-stripped."""
    pattern = rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>"
    return [m.strip() for m in re.findall(pattern, string, re.DOTALL)]


def parse_action(text:str)->list:

    actions=parse_xml(tag="action",string=text)

    bash_actions=list(itertools.chain.from_iterable([parse_xml(tag="bash",string=action) for action in actions]))
    message_actions=list(itertools.chain.from_iterable([parse_xml(tag="message",string=action) for action in actions]))
    exit_actions=list(itertools.chain.from_iterable([parse_xml(tag="exit",string=action) for action in actions]))

    return {"bash":bash_actions,"message":message_actions,"exit":exit_actions}

def main(prompt:str):

    messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt}]
    stop=False
    max_turns=5
    turn=0

    while not stop:
        turn+=1
        if turn>max_turns:
            break
        print(messages)
        response=llm_call(messages)
        print(response)
        actions=parse_action(response)

        print(actions)
        exit_action=actions.get("exit",None)
        if exit_action:
            break

        message_actions=actions.get("message",None)
        if message_actions:
            print(message_actions)
        
        bash_actions=actions.get("bash",None)
        if bash_actions:
            print(f"Bash: {bash_actions}")
            result=subprocess.run(bash_actions[0], capture_output=True,text=True,shell=True) 
            content=f"""
            Bash-Result:
            stdout: {result.stdout}
            stderr: {result.stderr}
            returncode: {result.returncode}
            """

            messages.append({"role":"user","content":content}) 


if __name__ == "__main__":

    import argparse
    parser=argparse.ArgumentParser("Coding agent from scratch")
    parser.add_argument("-p","--prompt",required=True,type=str,help="the prompt")
    args=parser.parse_args()

    main(prompt=args.prompt)

