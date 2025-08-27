from langchain_community.llms import Ollama

# Connect to Ollama container
llm = Ollama(model="qwen2.5:3b-instruct", base_url="http://ollama:11434")

