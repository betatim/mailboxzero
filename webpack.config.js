const webpack = require("webpack");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");


module.exports = {
  mode: "production", //"development",
  context: __dirname + "/mailboxzero/static/",
  entry: "./index.js",
  output: {
    path: __dirname + "/mailboxzero/static/dist/",
    filename: "bundle.js",
    publicPath: "/static/dist/"
  },
  module: {
    rules: [
      {
        test: /\.(scss)$/,
        use: [
          MiniCssExtractPlugin.loader,
          {
            // translates CSS into CommonJS modules
            loader: "css-loader"
          },
          {
            // Run postcss actions
            loader: "postcss-loader",
            options: {
              postcssOptions: {
                plugins: function() {
                  return [require("autoprefixer")];
                }
              }
            }
          },
          {
            // compiles Sass to CSS
            loader: "sass-loader"
          }
        ]
      },
      {
        test: /\.css$/,
        use: ["style-loader", "css-loader"]
      },
      {
        test: /\.(eot|woff|ttf|woff2|svg)$/,
        loader: "file-loader"
      },
      {
        test: /\.js$/,
        exclude: [/node_modules/, /js\/vendor/],
        use: [{ loader: "babel-loader" }]
      }
    ]
  },
  devtool: "source-map",
  plugins: [
    new MiniCssExtractPlugin({
      //filename: isProductionMode ? "[name].[contenthash].css" : "[name].css",
      filename: "[name].css",
    }),
  ],
};
