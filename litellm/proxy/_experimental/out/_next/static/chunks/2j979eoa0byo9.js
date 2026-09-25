(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push(["object"==typeof document?document.currentScript:void 0,191905,e=>{"use strict";var t=e.i(843476),n=e.i(466828),a=e.i(677572);let r=({proxySettings:e})=>{let r="<your_proxy_base_url>",s=e?.LITELLM_UI_API_DOC_BASE_URL;return s&&s.trim()?r=s:e?.PROXY_BASE_URL&&(r=e.PROXY_BASE_URL),(0,t.jsx)("div",{className:"grid grid-cols-1 gap-2 p-8 h-[80vh] w-full mt-2",children:(0,t.jsxs)("div",{className:"mb-5",children:[(0,t.jsx)("div",{className:"flex items-center justify-between",children:(0,t.jsx)("h1",{className:"text-2xl font-semibold text-foreground",children:"OpenAI Compatible Proxy: API Reference"})}),(0,t.jsxs)("p",{className:"mt-2 mb-2 text-sm text-muted-foreground",children:["RAW is OpenAI Compatible. This means your API Key works with the OpenAI SDK. Just replace the base_url to point to your RAW endpoint. Example Below"," "]}),(0,t.jsxs)(a.Tabs,{defaultValue:"openai",children:[(0,t.jsxs)(a.TabsList,{variant:"line",className:"border-b rounded-none w-full justify-start h-auto p-0",children:[(0,t.jsx)(a.TabsTrigger,{value:"openai",className:"rounded-none px-4 py-2 flex-none",children:"OpenAI Python SDK"}),(0,t.jsx)(a.TabsTrigger,{value:"llamaindex",className:"rounded-none px-4 py-2 flex-none",children:"LlamaIndex"}),(0,t.jsx)(a.TabsTrigger,{value:"langchain",className:"rounded-none px-4 py-2 flex-none",children:"Langchain Py"})]}),(0,t.jsx)(a.TabsContent,{value:"openai",keepMounted:!0,children:(0,t.jsx)(n.default,{language:"python",code:`import openai
client = openai.OpenAI(
    api_key="your_api_key",
    base_url="${r}" # RAW is OpenAI compatible
)

response = client.chat.completions.create(
    model="gpt-3.5-turbo", # model to send to the proxy
    messages = [
        {
            "role": "user",
            "content": "this is a test request, write a short poem"
        }
    ]
)

print(response)`})}),(0,t.jsx)(a.TabsContent,{value:"llamaindex",keepMounted:!0,children:(0,t.jsx)(n.default,{language:"python",code:`import os, dotenv

from llama_index.llms import AzureOpenAI
from llama_index.embeddings import AzureOpenAIEmbedding
from llama_index import VectorStoreIndex, SimpleDirectoryReader, ServiceContext

llm = AzureOpenAI(
    engine="azure-gpt-3.5",               # model_name on RAW
    temperature=0.0,
    azure_endpoint="${r}", # RAW endpoint
    api_key="<your-master-key>",          # RAW API Key
    api_version="2023-07-01-preview",
)

embed_model = AzureOpenAIEmbedding(
    deployment_name="azure-embedding-model",
    azure_endpoint="${r}",
    api_key="<your-master-key>",
    api_version="2023-07-01-preview",
)

documents = SimpleDirectoryReader("llama_index_data").load_data()
service_context = ServiceContext.from_defaults(llm=llm, embed_model=embed_model)
index = VectorStoreIndex.from_documents(documents, service_context=service_context)

query_engine = index.as_query_engine()
response = query_engine.query("What did the author do growing up?")
print(response)`})}),(0,t.jsx)(a.TabsContent,{value:"langchain",keepMounted:!0,children:(0,t.jsx)(n.default,{language:"python",code:`from langchain.chat_models import ChatOpenAI
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import HumanMessage, SystemMessage

chat = ChatOpenAI(
    openai_api_base="${r}",
    model = "gpt-3.5-turbo",
    temperature=0.1
)

messages = [
    SystemMessage(
        content="You are a helpful assistant that im using to make a test request to."
    ),
    HumanMessage(
        content="test from RAW. tell me why it's amazing in 1 sentence"
    ),
]
response = chat(messages)

print(response)`})})]})]})})};var s=e.i(541202),o=e.i(135214),i=e.i(592392);e.s(["default",0,()=>{let{accessToken:e}=(0,o.default)(),n=(0,i.default)(e);return(0,t.jsxs)(t.Fragment,{children:[(0,t.jsx)(s.DeprecationBanner,{featureName:"The API Reference tab"}),(0,t.jsx)(r,{proxySettings:n})]})}],191905)},541202,e=>{"use strict";var t=e.i(843476),n=e.i(271645),a=e.i(952571),r=e.i(37727);e.s(["DeprecationBanner",0,({featureName:e})=>{let[s,o]=(0,n.useState)(!1);return s?null:(0,t.jsxs)("div",{role:"alert",className:"mb-4 flex items-start gap-3 rounded-lg border border-border bg-muted/50 px-4 py-3 text-sm",children:[(0,t.jsx)(a.Info,{className:"mt-0.5 size-4 shrink-0 text-muted-foreground"}),(0,t.jsxs)("div",{className:"min-w-0 flex-1",children:[(0,t.jsx)("p",{className:"font-medium",children:`${e} is on a draft deprecation list`}),(0,t.jsx)("p",{className:"mt-1 break-words text-muted-foreground",children:`${e} is one of several experimental features we're considering removing, potentially as early as September 1, 2026. This list is a draft and is not final. If you rely on this feature, please contact your administrator.`})]}),(0,t.jsx)("button",{type:"button","aria-label":"Close",onClick:()=>o(!0),className:"shrink-0 rounded-md p-0.5 text-muted-foreground transition-colors hover:text-foreground",children:(0,t.jsx)(r.X,{className:"size-4"})})]})}])}]);