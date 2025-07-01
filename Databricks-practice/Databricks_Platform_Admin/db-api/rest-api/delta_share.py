# Providers
class DatabricksBaseAPI:
    DATABRICKS_INSTANCE = os.getenv('databricks_URL')
    TOKEN = os.getenv('PAT')
    HEADERS = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    @classmethod
    def list_assets_by_provider_share(cls, provider_name, share_name):
        return cls._get(f"/api/2.1/unity-catalog/providers/{provider_name}/shares/{share_name}/assets")

    @classmethod
    def list_providers(cls):
        return cls._get("/api/2.1/unity-catalog/providers")

    @classmethod
    def create_auth_provider(cls, data):
        return cls._post("/api/2.1/unity-catalog/providers", data)

    @classmethod
    def get_provider(cls, provider_name):
        return cls._get(f"/api/2.1/unity-catalog/providers/{provider_name}")

    @classmethod
    def update_provider(cls, provider_name, data):
        return cls._patch(f"/api/2.1/unity-catalog/providers/{provider_name}", data)

    @classmethod
    def delete_provider(cls, provider_name):
        return cls._delete(f"/api/2.1/unity-catalog/providers/{provider_name}")

    @classmethod
    def list_shares_by_provider(cls, provider_name):
        return cls._get(f"/api/2.1/unity-catalog/providers/{provider_name}/shares")

# Recipient Activation
class DeltaShareRecipientActivationAPI(DatabricksBaseAPI):
    @classmethod
    def get_access_token(cls, activation_url):
        return cls._post("/api/2.1/unity-catalog/recipients/activation-tokens", {"activation_url": activation_url})

    @classmethod
    def get_share_activation_url(cls, recipient_name):
        return cls._get(f"/api/2.1/unity-catalog/recipients/{recipient_name}/activation-url")

# Recipients
class DeltaShareRecipientsAPI(DatabricksBaseAPI):
    @classmethod
    def list_share_recipients(cls):
        return cls._get("/api/2.1/unity-catalog/recipients")

    @classmethod
    def create_share_recipient(cls, data):
        return cls._post("/api/2.1/unity-catalog/recipients", data)

    @classmethod
    def get_share_recipient(cls, recipient_name):
        return cls._get(f"/api/2.1/unity-catalog/recipients/{recipient_name}")

    @classmethod
    def update_share_recipient(cls, recipient_name, data):
        return cls._patch(f"/api/2.1/unity-catalog/recipients/{recipient_name}", data)

    @classmethod
    def delete_share_recipient(cls, recipient_name):
        return cls._delete(f"/api/2.1/unity-catalog/recipients/{recipient_name}")

    @classmethod
    def rotate_token(cls, recipient_name):
        return cls._post(f"/api/2.1/unity-catalog/recipients/{recipient_name}/rotate-token", {})

    @classmethod
    def get_recipient_share_permissions(cls, recipient_name):
        return cls._get(f"/api/2.1/unity-catalog/recipients/{recipient_name}/share-permissions")

# Shares
class DeltaShareSharesAPI(DatabricksBaseAPI):
    @classmethod
    def list_shares(cls):
        return cls._get("/api/2.1/unity-catalog/shares")

    @classmethod
    def create_share(cls, data):
        return cls._post("/api/2.1/unity-catalog/shares", data)

    @classmethod
    def get_share(cls, share_name):
        return cls._get(f"/api/2.1/unity-catalog/shares/{share_name}")

    @classmethod
    def update_share(cls, share_name, data):
        return cls._patch(f"/api/2.1/unity-catalog/shares/{share_name}", data)

    @classmethod
    def delete_share(cls, share_name):
        return cls._delete(f"/api/2.1/unity-catalog/shares/{share_name}")

    @classmethod
    def get_permissions(cls, share_name):
        return cls._get(f"/api/2.1/unity-catalog/shares/{share_name}/permissions")

    @classmethod
    def update_permissions(cls, share_name, data):
        return cls._patch(f"/api/2.1/unity-catalog/shares/{share_name}/permissions", data)