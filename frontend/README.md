# Jetson Nano Detection Dashboard Frontend

This is a simple Next.js App Router frontend for viewing the latest simulated object detection result.

The page polls the backend every 1 second and displays:

- `class_name`
- `confidence`
- `bbox`
- `timestamp`

This demo does not use Tailwind.

## Folder

```text
detection-demo/frontend/
  package.json
  app/
    layout.js
    page.js
  README.md
```

## Environment Variable

The frontend reads the backend URL from:

```text
NEXT_PUBLIC_API_URL
```

For local testing, if your Flask backend is running on port `5000`, use:

```text
NEXT_PUBLIC_API_URL=http://localhost:5000
```

For Vercel deployment, set:

```text
NEXT_PUBLIC_API_URL=https://your-railway-backend-url.up.railway.app
```

Do not add a trailing slash at the end of the URL.

## Run Locally

From this `frontend` folder:

```bash
npm install
```

Create a file named `.env.local`:

```text
NEXT_PUBLIC_API_URL=http://localhost:5000
```

Start the development server:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

## Deploy to Vercel

1. Push this project to GitHub.
2. Go to Vercel.
3. Import the GitHub repository.
4. Set the Vercel project root directory to:

```text
detection-demo/frontend
```

5. Add this environment variable in Vercel:

```text
NEXT_PUBLIC_API_URL=https://your-railway-backend-url.up.railway.app
```

6. Deploy the project.

After deployment, the Vercel frontend will fetch data from the Railway backend:

```text
https://your-railway-backend-url.up.railway.app/api/latest
```

## Remote Communication Flow

```text
fake detection sender PC -> Railway backend -> Vercel frontend viewer PC
```

The sender PC and viewer PC can be on different networks because they communicate through the deployed Railway and Vercel URLs.
