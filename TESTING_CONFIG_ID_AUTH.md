# Testing Configuration ID Based Meta OAuth

## Changes Made

### Backend:
1. Created `app/services/meta_config_service.py` - Configuration ID based service
2. Created `app/routes/meta_config_oauth.py` - New OAuth routes
3. Added endpoint in `app/routes/settings.py`: `/api/settings/meta/oauth/start-with-config`
4. Registered new router in `app/main.py`

### Frontend:
1. Added `startMetaOAuthWithConfigFromSettings()` function in `AdGenius/src/lib/api.ts`
2. Updated `Settings.tsx` to use Configuration ID based OAuth

### Environment Variables:
Add these to your `.env` file:
```
META_CONFIG_ID=your_meta_configuration_id_here
META_CONFIG_REDIRECT_URI=https://admin.growcommerce.app/api/meta-config/oauth/callback
```

## Testing Steps

1. Update `.env` with your Meta Configuration ID
2. Restart backend server
3. Go to Settings page in frontend
4. Click "Connect Meta Ads" button
5. It will now use Configuration ID instead of App ID

## API Endpoints

- Start OAuth: `GET /api/settings/meta/oauth/start-with-config`
- Callback: `GET /api/meta-config/oauth/callback`

## Note
- Onboarding page still uses App ID method (unchanged)
- Settings page now uses Configuration ID method
- Both methods work independently
