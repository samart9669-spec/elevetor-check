# Warehouse Flood Check — Streamlit + Supabase

## Files
- `app.py`: Streamlit app, GPS capture, A/B/C locations, terrain elevation estimate, risk checklist, shared history.
- `requirements.txt`: Python dependencies.
- `supabase_schema.sql`: create the shared table and prototype access policies.
- `.streamlit/secrets.toml.example`: template for app secrets.

## Deploy steps
1. Create a Supabase project at https://supabase.com/.
2. In Supabase, open SQL Editor and run `supabase_schema.sql`.
3. Copy the Project URL and the **publishable/anon key** (never use the service_role key in Streamlit app secrets).
4. In GitHub, create a repository and upload `app.py`, `requirements.txt`, and `supabase_schema.sql`.
5. Deploy the repository at https://share.streamlit.io/ and choose `app.py`.
6. In Streamlit app settings → Secrets, paste:
   ```
   SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
   SUPABASE_KEY = "YOUR_SUPABASE_PUBLISHABLE_OR_ANON_KEY"
   ```
7. Restart/redeploy. Test one record, then open the app in another browser to confirm shared history.

## Privacy and access warning
This prototype intentionally permits anonymous public reads and inserts so multiple users can share records without signing in. Anyone with the URL may view saved warehouse locations and add records. Do not store personal details or confidential notes. For a real public launch, add login, row-level permissions, spam protection, and a deletion/admin workflow. Never expose Supabase `service_role` key in client-facing or app code.

## Accuracy warning
Open-Meteo terrain elevation is a broad terrain-model estimate, not a survey of the exact road surface or warehouse floor. GPS altitude may be unavailable/inaccurate. Do not treat model differences as reliable centimeter-level measurements. Verify actual floor-to-road differences on site and ask about local flood history.
