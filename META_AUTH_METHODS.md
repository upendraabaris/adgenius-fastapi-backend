# Meta OAuth Authentication Methods

This application supports two methods for Meta OAuth authentication:

## Method 1: App ID Based Authentication (Existing)

This is the original method that uses Meta App ID and App Secret.

### Environment Variables:
```
META_APP_ID=1520651522382486
META_APP_SECRET=9e84e69725e0ebf0df0d623a1a1f1ed4
META_REDIRECT_URI=https://admin.growcommerce.app/api/meta/oauth/callback
```

### API Endpoints:
- **Start OAuth**: `GET /api/meta/oauth/start`
- **OAuth Callback**: `GET /api/meta/oauth/callback`
- **Settings Start**: `GET /api/settings/meta/oauth/start`

### Service File:
- `app/services/meta_service.py`

### Routes File:
- `app/routes/meta_oauth.py`

---

## Method 2: Configuration ID Based Authentication (New)

This is the new method that uses Meta Configuration ID instead of App ID.

### Environment Variables:
```
META_CONFIG_ID=your_meta_configuration_id_here
META_CONFIG_REDIRECT_URI=https://admin.growcommerce.app/api/meta-config/oauth/callback
```

### API Endpoints:
- **Start OAuth**: `GET /api/meta-config/oauth/start`
- **OAuth Callback**: `GET /api/meta-config/oauth/callback`
- **Settings Start**: `GET /api/settings/meta/oauth/start-with-config`

### Service File:
- `app/services/meta_config_service.py`

### Routes File:
- `app/routes/meta_config_oauth.py`

---

## How to Use

### For App ID Method (Existing):
```javascript
// Frontend code
const response = await fetch('/api/settings/meta/oauth/start', {
  headers: { Authorization: `Bearer ${token}` }
});
const { authUrl } = await response.json();
window.location.href = authUrl;
```

### For Configuration ID Method (New):
```javascript
// Frontend code
const response = await fetch('/api/settings/meta/oauth/start-with-config', {
  headers: { Authorization: `Bearer ${token}` }
});
const { authUrl } = await response.json();
window.location.href = authUrl;
```

---

## Key Differences

| Feature | App ID Method | Configuration ID Method |
|---------|--------------|------------------------|
| OAuth Parameter | `client_id` | `config_id` |
| Token Exchange | Uses `client_id` + `client_secret` | Uses `config_id` |
| Scope Parameter | `ads_read` | Not required (configured in Meta) |
| Auth Type | `rerequest` | Not required |

---

## Notes

- Both methods store the integration in the same `integrations` table with `provider='meta'`
- Both methods fetch the same ad account data after authentication
- The Configuration ID method is more flexible as permissions are managed in Meta's dashboard
- You can switch between methods by changing which endpoint you call from the frontend
