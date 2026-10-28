# retailops-ai

An AI-Agent built with **FastAPI** that translates natural language questions into executable SQL queries.

## Getting Started

Follow these steps to set up and run the project locally.

### 1. Environment Variables
Create a `.env` file by copying the example file:

```bash
cp .env.example .env
```

### 2. Install Dependencies
Navigate to the `src` directory and install the required packages:

```bash
cd src
pip install -r requirements.txt
```

### 3. Run the Server
Start the development server using Uvicorn (make sure you are inside the `src` directory):

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

## API & Documentation Links

Once the server is running, you can access the API and its documentation via the following URLs:

- **Local development API base URL:** `http://localhost:5000`
- **Local development Swagger UI:** `http://localhost:5000/docs`
- **Local development Scalar API reference:** `http://localhost:5000/scalar`