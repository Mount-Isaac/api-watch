# Changelog

## Version 0.1.5 (Released)
1. Persistent data storage
   - sqlite3
2. FastAPI capture & log response data
   - currently prints request data & headers

## Version 2.0.0 (Released)
1. Remove code integration
   - FastAPI
   - Flask
2. Watch Docker containers for logs
   - stream logs
   - add labels to monitor containers

## Version 2.1.0 (Released)
1. UI redesign pass
   - fixed border radius bleeding into accent borders on cards and log rows
   - reworked color palette and fonts (Inter for UI, Roboto Mono for logs)
   - added active view highlight, shows which log row you're currently reading
   - restored login page to prior behavior after user feedback
2. Bug fixes
   - fixed alert toggle switch styling regression
   - fixed light mode contrast on hover and card backgrounds

## Next Release: Version 2.1.1
1. Log retention controls
   - configurable retention period, old entries automatically pruned to prevent unbounded growth
   - per-container quotas (on roadmap, pending demand)
   - size-based retention as an alternative to time-based (on roadmap, pending demand)

## Next Release: Version 2.1.2
1. Container analysis dashboards