import httpx


OLLAMA_ENDPOINT="http://localhost:11434/api/chat"
MODEL="glm-5.2:cloud"
SYSTEM_PROMPT="""You're an autonomous coding agent.

You can perform exactly three actions by wrapping your answer in xml-tags 
- exit -  
- continue / message
- callbash
Whenever you wan't to execute a bash-command, wrap the bash-command in xml-tags <bash-action> COMMAND </bash-action>.
Return only the xml-tags.
Once youre finished, answer with 'Finished'



{"type": "message", "content":

# Example 1: Listing the content of a directory
<action>
<bash>ls -alh /path/to/dir</bash>
</action>

# Example 2: 
<action>
<bash> wc -l path/to/file</bash>
</action>

# Example 3: 
<action>
<exit> Final Message</exit>
</action>

# Example 4: 
<action>
<message> Message</message>
</action>



"""



def call_llm(messages:list)->
    r=httpx.post(OLLAMA_ENDPOINT,json={"model":MODEL,"stream":False, "messages":messages},timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]


def parse_action(text:str)->str:
    tag="bash-action"
    """All contents of <tag>...</tag>, in order of appearance, whitespace-stripped."""
    pattern = rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>"
    return [m.strip() for m in re.findall(pattern, text, re.DOTALL)]


messages=[{"role":"user","content":question}]
stop=False
max_turns=50
turn=0
while not stop:
    turn+=1
    if turn>max_turns:
        break

    response=llm_call(messages)
    
    if response.type=="final_answer":
        break

    if response.
        parse_action() 
    if response.typ



if __name__ == "__main__":

    import argparse
    parser=argparse.ArgumentParser("Coding agent from scratch")
    parser.add_argument("-p","--prompt",required=True,type=str,help="the prompt")
    args=parser.parse_args()


    main(prompt=args.prompt)

