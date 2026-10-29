from flask import Flask, render_template, request

app = Flask(__name__)


# Sample food listings
food_listings = [
    {
        "id": 1,
        "name": "Fresh Bakery Bread",
        "category": "Bakery",
        "description": "Freshly baked loaves available at a discount.",
        "original_price": 2000,
        "discounted_price": 1200,
        "quantity": 15,
        "location": "Yaba, Lagos",
        "collection_deadline": "7:00 PM",
        "emoji": "🥖"
    },
    {
        "id": 2,
        "name": "Fresh Vegetable Basket",
        "category": "Fruits & Vegetables",
        "description": "A selection of fresh seasonal vegetables.",
        "original_price": 5000,
        "discounted_price": 3000,
        "quantity": 8,
        "location": "Ikeja, Lagos",
        "collection_deadline": "6:00 PM",
        "emoji": "🥦"
    },
    {
        "id": 3,
        "name": "Chicken Sandwich",
        "category": "Prepared Meals",
        "description": "Ready-to-eat chicken sandwiches.",
        "original_price": 3500,
        "discounted_price": 2100,
        "quantity": 6,
        "location": "Surulere, Lagos",
        "collection_deadline": "5:30 PM",
        "emoji": "🥪"
    },
    {
        "id": 4,
        "name": "Fresh Fruit Pack",
        "category": "Fruits & Vegetables",
        "description": "A pack of fresh, seasonal fruit.",
        "original_price": 4000,
        "discounted_price": 2500,
        "quantity": 10,
        "location": "Lekki, Lagos",
        "collection_deadline": "6:30 PM",
        "emoji": "🍎"
    },
    {
        "id": 5,
        "name": "Assorted Pastries",
        "category": "Bakery",
        "description": "A selection of assorted bakery pastries.",
        "original_price": 3000,
        "discounted_price": 1800,
        "quantity": 12,
        "location": "Victoria Island, Lagos",
        "collection_deadline": "7:30 PM",
        "emoji": "🥐"
    },
    {
        "id": 6,
        "name": "Rice Meal Pack",
        "category": "Prepared Meals",
        "description": "A freshly prepared rice meal.",
        "original_price": 4500,
        "discounted_price": 3000,
        "quantity": 5,
        "location": "Yaba, Lagos",
        "collection_deadline": "5:00 PM",
        "emoji": "🍱"
    }
]


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/marketplace")
def marketplace():
    search_query = request.args.get("search", "").strip()
    selected_category = request.args.get("category", "").strip()

    filtered_listings = []

    for food in food_listings:
        if food["quantity"] <= 0:
            continue

        matches_search = (
            search_query.lower() in food["name"].lower()
            or search_query.lower() in food["description"].lower()
            or search_query.lower() in food["location"].lower()
        )

        matches_category = (
            not selected_category
            or food["category"] == selected_category
        )

        if matches_search and matches_category:
            food_copy = food.copy()

            food_copy["discount_percentage"] = round(
                (
                    food["original_price"]
                    - food["discounted_price"]
                )
                / food["original_price"]
                * 100
            )

            filtered_listings.append(food_copy)

    categories = sorted(
        {food["category"] for food in food_listings}
    )

    return render_template(
        "marketplace.html",
        food_listings=filtered_listings,
        categories=categories,
        search_query=search_query,
        selected_category=selected_category
    )


if __name__ == "__main__":
    app.run(debug=True)