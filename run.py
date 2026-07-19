from ouroboros_financial_management import create_app

app = create_app()

if __name__ == "__main__":
    # Localhost only. Do not change host to 0.0.0.0 unless you intentionally want LAN exposure.
    app.run(host="127.0.0.1", port=5000, debug=False)
