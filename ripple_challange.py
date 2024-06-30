import streamlit as st
import requests
from openai.types.beta.assistant_stream_event import ThreadMessageCompleted, ThreadRunFailed
from openai import OpenAI
from crawl_util import CrawlUtil
import xrpl
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.transaction import  autofill_and_sign,sign_and_submit,submit_and_wait
from xrpl.models.transactions import Payment
from xrpl.models.requests import AccountInfo
test_wallet_address = st.secrets["TEST_WALLET_ADDRESS"]
test_wallet_secret = st.secrets["TEST_WALLET_SECRET"]


def send_xrp_test(destination_address,amount_xrp):
    JSON_RPC_URL = "https://s.altnet.rippletest.net:51234/"
    client = JsonRpcClient(JSON_RPC_URL)
    # Create a wallet from the testnet credentials
    test_wallet = Wallet.from_seed(test_wallet_secret)

    # Define the destination address and amount to send (in drops, 1 XRP = 1,000,000 drops)
    destination_address = destination_address
    amount_to_send = amount_xrp  # Example: sending 5 XRP (5,000,000 drops)

    # Check the balance of the sender account before the transaction
    account_info = AccountInfo(
        account=test_wallet.classic_address,
        ledger_index="validated"
    )
    response = client.request(account_info)
    print(f"Balance before transaction: {response.result['account_data']['Balance']} drops")

    # Prepare the payment transaction
    payment_tx = Payment(
        account=test_wallet.classic_address,
        amount=amount_to_send,
        destination=destination_address
    )

    # Sign and autofill the transaction
    signed_tx = autofill_and_sign(payment_tx, client, test_wallet)

    # Submit the transaction
    response = submit_and_wait(signed_tx, client)

    # Check the balance of the sender account after the transaction
    response = client.request(account_info)


def get_xrp_info(address):
    url = f"https://api.xrpscan.com/api/v1/account/{address}"
    
    response = requests.get(url)
    if response.status_code == 200:
        account_info = response.json()
        st.write(account_info)
        if 'accountName' not in account_info or account_info['accountName'] is None:
            return None, None, None, None, None  # No accountName, return early
        
        domain = account_info['accountName'].get('domain', None)
        verified = account_info.get('accountName', {}).get('verified', False)
        twitter = account_info['accountName'].get('twitter', None)
        balance = account_info.get('xrpBalance', None)
        initial_balance = account_info.get('initial_balance', None)
        return verified, domain, twitter, balance, initial_balance
    else:
        st.error(f"Error fetching data: {response.status_code}")
        return None, None, None, None, None

def app():
    # ======================= OpenAI configuration =======================
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    vector_storage_id = st.secrets["VECTOR_STORAGE_ID"]
    report_assistant_id = st.secrets["ASSISTANT_ID"]
    summary_assistant_id = st.secrets["SUMMARY_ASSISTANT"]
    resource_assistant_id = st.secrets["RESOURCE_ASSISTANT"]

    # ======================= Crawling business information =======================
    progress_text = "Operation in progress. Please wait."
    web_crawler = CrawlUtil(
        client=client, vector_storage_id=vector_storage_id, progress_text=progress_text
    )

    # Hide Streamlit style
    hide_streamlit_style = """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)

    # Sidebar content
    with st.sidebar:
        st.warning("""
            🕵️ Sweephy Ripple Challange and Risk AI presents\n
            Enter your wallet address to find which risk might affect your transaction
        """)

    # ================ Main Search UI =======================
    st.title('Regulation risk AI by Sweephy on XRP Ledger')
    st.markdown('---')

    emp = st.empty()

    with emp.form("Magic form"):
        # ======================= User Inputs =======================
        wallet_address = st.text_input("Enter your destination XRP wallet address", placeholder="e.g., rMdG3ju8pgyVh29ELPWaDuA74CpWW6Fxns")
        amount_xrp = st.number_input("Enter the XRP amount that you would like to send!")
        submitted = st.form_submit_button("Check Destination ✨✨")

        if submitted:
            with st.spinner('Fetching account information...'):
                # ======================= Fetch domain information =======================
                verified, domain, twitter, balance, initial_balance = get_xrp_info(wallet_address)
                if not domain:
                    st.error("No info")
                    return

                if not twitter or not balance or not initial_balance:
                    st.error("There is no sufficient information available for this address.")
                    return

                st.success('Account information retrieved successfully!')

            # ======================= Crawling business information =======================
            my_bar = st.progress(0, text=progress_text)
            with st.spinner('Crawling business information...'):
                web_crawler.website_crawler(f"https://{domain}", my_bar=my_bar)

            st.write("### Crawling business information...")
            company_name = web_crawler.extract_company_from_url(f"https://{domain}")

            # ======================= Summary information =======================
            summary_prompt = f"Provide a brief summary of the financial regulations relevant to the company: {company_name}"
            # ======================= Report information =======================
            report_prompt = f"Identify any financial compliance red flags in the company data: {company_name} that might affect their business compliance."
            # ======================= Resource information =======================
            resource_prompt = f"List the relevant financial regulatory documents for the company: {company_name}"

            assistants_ = {
                'resource': resource_assistant_id,
                'report': report_assistant_id,
                'summary': summary_assistant_id,
            }
            prompts_ = {
                'resource': resource_prompt,
                'report': report_prompt,
                'summary': summary_prompt,
            }

            def run_assistant(prompt, assistant_id):
                thread = client.beta.threads.create(
                    messages=[
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": prompt}],
                        }
                    ]
                )
                run = client.beta.threads.runs.create(
                    thread_id=thread.id, assistant_id=assistant_id, stream=True
                )

                result_text = ""
                for event in run:
                    if isinstance(event, ThreadMessageCompleted):
                        result_text = event.data.content[0].text.value
                    if isinstance(event, ThreadRunFailed):
                        print(event)
                        break
                return result_text

            # ======================= Start AI assistants =======================
            results = {}
            for key in assistants_.keys():
                results[key] = run_assistant(
                    prompt=prompts_[key],
                    assistant_id=assistants_[key]
                )

            st.markdown('---')
            report_container = st.container()
            with report_container:
                st.subheader("Summary")
                st.markdown(f"<div style='background-color: #f9f9f9; padding: 10px; border-radius: 5px;'>{results.get('summary', '')}</div>", unsafe_allow_html=True)
                st.subheader("Report")
                st.markdown(f"<div style='background-color: #f9f9f9; padding: 10px; border-radius: 5px;'>{results.get('report', '')}</div>", unsafe_allow_html=True)
                st.subheader("Resources")
                st.markdown(f"<div style='background-color: #f9f9f9; padding: 10px; border-radius: 5px;'>{results.get('resource', '')}</div>", unsafe_allow_html=True)
                st.markdown('---')
                st.subheader("XRP Account Information")
                st.markdown(
                    f"""
                    <div style="background-color: #f9f9f9; padding: 10px; border-radius: 5px;">
                        <strong>Verified:</strong> {'Yes' if verified else 'No'}<br>
                        <strong>Domain:</strong> {domain}<br>
                        <strong>Twitter:</strong> {twitter}<br>
                        <strong>Balance:</strong> {balance}<br>
                        <strong>Initial Balance:</strong> {initial_balance}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
    send_xrp_container = st.container()
    with send_xrp_container:
        if st.button("Send the amount"):
            send_xrp_test(wallet_address,amount_xrp)
                

if __name__ == "__main__":
    st.set_page_config(
        page_title='Ripple Transaction - Risk AI by Sweephy',
        page_icon="LogoLeaf.png",
        layout='wide',
        initial_sidebar_state='auto',
    )
    app()