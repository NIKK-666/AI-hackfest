from flask import Flask, render_template, request, send_file, redirect, url_for, flash
import pandas as pd
import numpy as np
import joblib
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv
import google.generativeai as genai
from flask import request, jsonify


# Load Gemini API
genai.configure(api_key=os.getenv(""))
model = genai.GenerativeModel('Gemini 2.0 Flash')

load_dotenv()

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
MODEL_PATH = "model/model.joblib"
app.secret_key = "your_secret_key"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static", exist_ok=True)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    try:
        response = model.generate_content(user_message)
        return jsonify({"response": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", download=False, counts=None, plot_url=None)

@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "GET":
        return redirect(url_for("index"))

    if "csv_file" not in request.files:
        flash("No file part")
        return redirect(url_for("index"))

    file = request.files["csv_file"]

    if file.filename == "":
        flash("No selected file")
        return redirect(url_for("index"))

    if not file.filename.endswith(".csv"):
        flash("Invalid file type. Please upload a CSV file.")
        return redirect(url_for("index"))

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    try:
        file.save(filepath)
    except Exception as e:
        flash(f"Error saving file: {e}")
        return redirect(url_for("index"))

    try:
        df = pd.read_csv(filepath)
        model = joblib.load(MODEL_PATH)

        X = df.select_dtypes(include=["number"]).replace([np.inf, -np.inf], np.nan)
        X.dropna(inplace=True)
        df_processed = df.iloc[X.index].copy()

        if hasattr(model, 'n_features_in_'):
            expected = model.n_features_in_
        elif hasattr(model, 'feature_names_in_'):
            expected = len(model.feature_names_in_)
        else:
            expected = X.shape[1]

        if X.shape[1] > expected:
            X = X.iloc[:, :expected]
        elif X.shape[1] < expected:
            missing_cols = [f"missing_col_{i}" for i in range(expected - X.shape[1])]
            for col in missing_cols:
                X[col] = 0
            if hasattr(model, 'feature_names_in_'):
                try:
                    X = X[list(model.feature_names_in_)]
                except KeyError as e:
                    flash(f"Error: Model feature names do not match the columns in the uploaded CSV. Missing column: {e}")
                    return redirect(url_for("index"))

        preds = model.predict(X.to_numpy())
        df_processed["anomaly"] = preds
        df_processed["anomaly_label"] = df_processed["anomaly"].map({1: "Anomaly", -1: "Normal"})

        result_path = os.path.join(UPLOAD_FOLDER, "result.csv")
        df_processed.to_csv(result_path, index=False)

        # Plotting
        plot_path = None
        if X.shape[1] >= 2:
            plt.figure(figsize=(8, 6))

            if "anomaly_label" in df_processed and not df_processed["anomaly_label"].isnull().all():
                sns.scatterplot(
                    x=X.iloc[:, 0],
                    y=X.iloc[:, 1],
                    hue=df_processed["anomaly_label"],
                    palette={"Anomaly": "#ff7b72", "Normal": "#238636"},
                    s=60
                )
            else:
                sns.scatterplot(x=X.iloc[:, 0], y=X.iloc[:, 1], s=60, color="#58a6ff")

            plt.title("Anomaly Detection Results", color="#58a6ff")
            plt.xlabel(X.columns[0], color="#c9d1d9")
            plt.ylabel(X.columns[1], color="#c9d1d9")
            plt.tick_params(axis='x', colors='#c9d1d9')
            plt.tick_params(axis='y', colors='#c9d1d9')
            plt.grid(True, color="#30363d", linestyle='--', alpha=0.7)

            plot_path = os.path.join("static", "result_plot.png")
            plt.savefig(plot_path, facecolor="#0d1117")
            plt.close()

        counts = df_processed["anomaly_label"].value_counts().to_dict()
        return render_template("index.html", counts=counts, plot_url=plot_path, download=True)

    except (FileNotFoundError, joblib.ReadError):
        flash("Error: Model or data file not found.")
        return redirect(url_for("index"))
    except KeyError as e:
        flash(f"Error: Missing column in CSV: {e}")
        return redirect(url_for("index"))
    except pd.errors.EmptyDataError:
        flash("Error: The uploaded CSV file is empty.")
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"Error processing file: {e}")
        return redirect(url_for("index"))

@app.route("/download")
def download():
    return send_file("uploads/result.csv", as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
