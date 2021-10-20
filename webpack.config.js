const path = require('path')
const glob = require('glob')
const webpack = require("webpack");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const PurgecssPlugin = require('purgecss-webpack-plugin')

const PATHS = {
  src: path.join(__dirname, 'mailboxzero')
}

module.exports = {
  mode: "production",
  //mode: "development",
  context: __dirname + "/mailboxzero/static/",
  entry: "./index.js",
  output: {
    path: __dirname + "/mailboxzero/static/dist/",
    filename: "bundle.js",
    publicPath: "/static/dist/"
  },
  optimization: {
    splitChunks: {
      cacheGroups: {
        styles: {
          name: 'styles',
          test: /\.css$/,
          chunks: 'all',
          enforce: true
        }
      }
    }
  },
  module: {
    rules: [
      {
        test: /\.(scss)$/,
        use: [
          MiniCssExtractPlugin.loader,
          {
            // translates CSS into CommonJS modules
            loader: "css-loader",
            options: {
              importLoaders: 1
            }
          },
          {
            loader: "postcss-loader",
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
      filename: "[name].css",
    }),
    new PurgecssPlugin({
      paths: glob.sync(`${PATHS.src}/**/*`,  { nodir: true }),
      //safelist: [ /.*file-selector-button.*/],
      variables: true,
      rejected: true,
    }),
  ],
};
