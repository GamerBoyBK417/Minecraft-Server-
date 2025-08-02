from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def viewer():
    url = "https://gamep.cloudcrash.shop"  # Your protected link
    return render_template("viewer.html", url=url)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
