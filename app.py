from flask import Flask, render_template, request, send_file
import pandas as pd
import numpy as np
import joblib
import os
import matplotlib
matplotlib.use("Agg")  # Use non-GUI backend for matplotlib
import matplotlib.pyplot as plt
import seaborn as sns

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
MODEL_PATH = "model/model.joblib"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    counts = None
    plot_url = None
    download_enabled = False

    if request.method == "POST":
        file = request.files["csv_file"]
        if not file:
            return "No file uploaded."

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        try:
            file.save(filepath)

            # Load data
            df = pd.read_csv(filepath)

            # Load model
            try:
                model = joblib.load(MODEL_PATH)
            except FileNotFoundError:
                return "Error: Model file not found at {}".format(MODEL_PATH)

            # Handle only numeric columns
            X = df.select_dtypes(include=["number"]).replace([np.inf, -np.inf], np.nan)
            X.dropna(inplace=True)
            df = df.iloc[X.index].copy()  # Sync with X, use copy to avoid SettingWithCopyWarning

            # Handle shape mismatch
            if hasattr(model, 'n_features_in_'):
                n_features_expected = model.n_features_in_
            elif hasattr(model, 'feature_names_in_'):
                n_features_expected = len(model.feature_names_in_)
            else:
                n_features_expected = X.shape[1] # Fallback

            n_features_actual = X.shape[1]

            if n_features_actual > n_features_expected:
                X = X.iloc[:, :n_features_expected]
            elif n_features_actual < n_features_expected:
                missing = n_features_expected - n_features_actual
                for i in range(missing):
                    X[f"missing_col_{i}"] = 0
                # Ensure the order of columns matches the training data if feature_names_in_ exists
                if hasattr(model, 'feature_names_in_'):
                    expected_cols = list(model.feature_names_in_) + [col for col in X.columns if col not in model.feature_names_in_]
                    X = X[expected_cols]
                elif n_features_actual + missing == n_features_expected:
                     # Pad with zeros, order might still be off if names weren't stored
                     pass


            # Predict
            df["anomaly"] = model.predict(X.to_numpy())

            # Save result
            result_path = os.path.join(UPLOAD_FOLDER, "result.csv")
            df.to_csv(result_path, index=False)

            # Ensure 'static' directory exists
            os.makedirs("static", exist_ok=True)

            # Plot (only if at least 2 features exist)
            if X.shape[1] >= 2:
                plt.figure(figsize=(8, 6))
                sns.scatterplot(
                    x=X.iloc[:, 0], y=X.iloc[:, 1], hue=df["anomaly"],
                    palette={1: "green", -1: "red"}, s=60
                )
                plt.title("Anomaly Detection Results")
                plot_path = "static/result_plot.png"
                plt.savefig(plot_path)
                plt.close()
                plot_url = plot_path
            else:
                plot_url = None
                print("Warning: Not enough features (at least 2) to generate a 2D plot.")

            # Anomaly stats
            counts = df["anomaly"].value_counts().to_dict()
            download_enabled = True

        except FileNotFoundError:
            return "Error: Uploaded file not found."
        except Exception as e:
            return f"An error occurred: {e}"

    return render_template("index.html", counts=counts, plot_url=plot_url, download=download_enabled)

@app.route("/download")
def download():
    return send_file("uploads/result.csv", as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)