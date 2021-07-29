import './main.scss';

import LocalTime from "local-time"
LocalTime.start()

import * as Turbo from "@hotwired/turbo"

import { Application } from "stimulus"
import { definitionsFromContext } from "stimulus/webpack-helpers"

const application = Application.start()
const context = require.context("./controllers", true, /\.js$/)
application.load(definitionsFromContext(context))

// Unclear if we need this or not
//Turbo.start()
