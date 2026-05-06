# Mortgage origination demo

## Purpose
The purpose of this demo is to demonstrate how the mesh works using a real-life agentic automation example: a mortgage origination process in a bank. 

## Business requirements
The end-user will complete the mortgage origination journey by chatting to a Customer Agent via a web interface. The end-user can upload relevant documents (passport for KYC/identification, payslips as proof of income). 

The journey looks like this: 

- End-user greets the Customer Agent / says hello
- Customer Agent asks the end-user to identify themselves using a BAN (bank account number) and PIN. The Customer Agent invokes the Authentication agent, which verifies the BAN and PIN against the Customer Master system via MCP. Any value is accepted for now, there is no validation.
- End-user is asked to upload proof of identity. The end-user does this. Customer Agent talks to KYC agent (see helow) that cheecks identity against KYC system via MCP
- End-user is asked to upload payslips. The Customer Agent extracts the monthly salary information from the payslip, estimates the annual salary and confirms the amount with the end-user. The Customer Agent then talks to the Credit Agent, which asssesses how much the end-user can borrow (max loan capacity) by invoking the credit decisioning system via MCP. The Credit Agent sends that information back to the Customer Agent
- Customer Agent informs the end-user of their maximum loan capacity and asks if (a) if they wish to go ahead with the home loan, (b) if yes, their deposit, and (c) if yes, the address details and value of the property they wish to buy
- Customer Agent then sends those details to Credit Agent, which invokes the credit decisioning model via MCP. The model returns a loan decision (approved/denied)
- The Customer Agent informs the end-user of the credit decision / outcome. If it is a yes, the next step is to ask if they have bid for the property
- The Customer Agent then asks the customer to upload the executed contract of purchase
- Once uploaded, the Customer Agent interacts with the Core Banking Agent and asks it to disburse the loan amount to the customer's account. The Core Banking Agent then talks to the core banking system via MCP and disburses the loan amount to their account identified by the BAN. 
- The Customer Agent informs tne end-user that the loan amount has been disbursed to their account.
- The Customer Agent says good luck and the conversation ends

## Architecture
The Customer Agent interacts with the user via the web interfaace and orchestrates and interacts with a set of sub agents that complete the journey. The following agents are part of the journey: 

- Authentication agent - authenticates the customer using BAN and PIN via MCP to the bank's customer master system (API)
- KYC agent - verifies the customer's identity by talking to the bank's KYC system via MCP to the bank's KYC system (API)
- Credit agent - verifies the customer's loan capacity and final credit decision via MCP to the credit decisioning engine (API)
- Core Banking agent - disburses the loan amount to the customer's bank accoutn identified via the customer's BAN by talking to the core banking system via MCP (API)

The customer master system, KYC system, credit decisioning engine, and core banking system will be developed as *stubs* (they are not real systems) and accessed via APIs. The agents interact with these APIs using MCP.

The agents will use Anthropic models as the LLMs. These must be real LLMs.

The web interface will be developed in React.js / Vite, using the same architecture as the Registry. The bank's name is "Agentic Bank"

## Deployment
- Web interface, Customer agent and Authentication agent are deployed on the same Langgraph instance running in docker container 1
- Credit agent and KYC agent are deployed on a second Langgraph instance running in docker container 2
- Core Banking agent is deployed on a thrid Langgraph instance running in docker container 3

The following constraints apply and must be enforced in the mesh: 

- On deployment of the entire demo, wipe the agents in the database
- ALL agents are to be submitted via the submission API. You cannot hardcode them. They will have to undergo security and evaluation and manual approval in the registry
- Customer Agent can talk to all other agents. All other agents can only interact with Customer agent. For instance, Credit agent cannot talk to Core Banking agent and so forth. This should be enforced using policies in the mesh. 
