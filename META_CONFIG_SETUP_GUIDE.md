# Meta Configuration ID Setup Guide

## Problem
Getting "Invalid App ID" error when using Configuration ID for OAuth.

## Solution

### Step 1: Check Your .env File
Make sure these variables are set correctly:
```env
META_CONFIG_ID=1312983024074117
META_CONFIG_REDIRECT_URI=https://admin.growcommerce.app/api/meta-config/oauth/callback
```

### Step 2: Meta Developer Console Setup

1. Go to https://developers.facebook.com/apps/
2. Select your app (ID: 1520651522382486)
3. Go to "App Settings" → "Advanced" → "OAuth Settings"
4. Add this redirect URI:
   ```
   https://admin.growcommerce.app/api/meta-config/oauth/callback
   ```

### Step 3: Create Configuration ID (if not already created)

1. In Meta Developer Console, go to "Marketing API" settings
2. Look for "System User Access Tokens" or "Configuration"
3. Create a new Configuration with:
   - Redirect URI: `https://admin.growcommerce.app/api/meta-config/oauth/callback`
   - Permissions: `ads_read`
4. Copy the Configuration ID

### Step 4: Verify Backend Logs

After restarting backend, check logs for:
```
🔧 Starting OAuth with Configuration ID: 1312983024074117
🔧 Redirect URI: https://admin.growcommerce.app/api/meta-config/oauth/callback
🔧 Generated OAuth URL: ...
```

## Alternative: Use App ID Method (Already Working)

If Configuration ID is causing issues, you can temporarily switch back to App ID:

In `AdGenius/src/pages/Settings.tsx`, change:
```typescript
const result = await startMetaOAuthWithConfigFromSettings();
```
Back to:
```typescript
const result = await startMetaOAuthFromSettings();
```

This will use the working App ID method while you set up Configuration ID.
