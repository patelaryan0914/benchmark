const express = require("express");
const app = express();
const PORT = process.env.PORT || 3000;

// Middleware to parse JSON requests
app.use(express.json());

// Route to collect info from the function
app.post("/collect-info", async (req, res) => {
  const { info } = req.body; // Expecting info in the request body

  try {
    console.log(info);
    res
      .status(200)
      .json({ message: "Info collected successfully", data: response.data });
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error collecting info", error: error.message });
  }
});

// Start the server
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
