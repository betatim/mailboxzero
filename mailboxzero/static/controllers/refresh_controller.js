
import * as Turbo from "@hotwired/turbo"
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static values = { interval: Number, src: String }

  initialize() {
    this.handleVisibility = this._handleVisibility.bind(this)
  }

  startRefreshing() {
    this.refreshTimer = setInterval(() => {
      this.reload()
    }, this.intervalValue)
  }

  stopRefreshing() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer)
    }
  }

  reload() {
    this.element.removeAttribute("src")
    this.element.setAttribute("src", this.srcValue)
  }

  _handleVisibility() {
    if (document.visibilityState === "hidden") {
      this.stopRefreshing()
    } else {
      this.reload()
      this.startRefreshing()
    }
  }

  connect() {
    if (this.hasIntervalValue) {
      this.startRefreshing()
      document.addEventListener("visibilitychange", this.handleVisibility)
    }
  }

  disconnect() {
    this.stopRefreshing()
    window.removeEventListener("visibilitychange", this.handleVisibility)
  }
}
