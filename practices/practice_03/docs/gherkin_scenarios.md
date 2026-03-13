# Gherkin Scenarios — Подписка на утреннюю сводку (v1.0)

```gherkin
Feature: Morning email digest subscription v1.0

  Background:
    Given the WeatherService API is running
    And PostgreSQL is available and the subscriptions table is empty for test emails
    And Redis is available and empty for keys related to test cities
    And OpenWeatherMap API is reachable for city validation

  Scenario 1: Create morning digest subscription for a valid city and return weather data (happy path)
    Given a user has entered email "user1@example.com" and selected notification type "morning digest" in the subscription form
    And the user has chosen city "Helsinki"
    When the client sends POST "/subscribe" with JSON:
    {"city":"Helsinki","email":"user1@example.com"}
    Then the response status code should be 201
    And the response body should include "city" = "Helsinki"
    And the response body should include weather data fields
    And a subscription record should be created in PostgreSQL with:
      | email             | city     | notification_time | status   |
      | user1@example.com | Helsinki | morning           | pending  |
    And a confirmation email should be sent to "user1@example.com" containing a confirmation link

  Scenario 2: Confirm subscription via email link and activate it
    Given an existing pending subscription in PostgreSQL for:
      | email             | city     | notification_time | status  |
      | user2@example.com | Tallinn  | morning           | pending |
    And a confirmation token exists for "user2@example.com" and city "Tallinn"
    When the user opens the confirmation link for that token
    Then the response status code should be 200
    And the subscription record in PostgreSQL should be updated to status "active"
    And the user should see a confirmation message that the subscription is activated

  Scenario 3: Weather data is cached in Redis for 10 minutes after subscription
    Given the city "Oslo" is valid in OpenWeatherMap
    And there is no Redis cache entry for city "Oslo"
    When the client sends POST "/subscribe" with JSON:
      {"city":"Oslo","email":"user3@example.com"}
    Then the response status code should be 201
    And Redis should contain a cache entry for city "Oslo" with TTL of 600 seconds
    And the cached value should contain weather data matching the response body

  Scenario 4: Reject subscription when city does not exist (negative)
    Given a user has entered email "user4@example.com" and selected notification type "morning digest" in the subscription form
    And the user has chosen city "NoSuchCity_12345"
    When the client sends POST "/subscribe" with JSON:
      {"city":"NoSuchCity_12345","email":"user4@example.com"}
    Then the response status code should be 400
    And the response body should include an error message about invalid or unknown city
    And no subscription record should be created in PostgreSQL for email "user4@example.com" and city "NoSuchCity_12345"
    And no confirmation email should be sent to "user4@example.com"

  Scenario 5: Reject duplicate subscription for same email and city (negative)
    Given an existing subscription in PostgreSQL for:
      | email             | city     | notification_time | status |
      | user5@example.com | Riga     | morning           | active |
    When the client sends POST "/subscribe" with JSON:
      {"city":"Riga","email":"user5@example.com"}
    Then the response status code should be 409
    And the response body should include an error message about duplicate subscription
    And no additional subscription record should be created in PostgreSQL for email "user5@example.com" and city "Riga"
    And no confirmation email should be sent to "user5@example.com"

  Scenario 6: Handle city input with extra spaces and special symbols (boundary)
    Given a user has entered email "user6@example.com" and selected notification type "morning digest" in the subscription form
    And the user has chosen city "  São   Paulo!!!  "
    When the client sends POST "/subscribe" with JSON:
      {"city":"  São   Paulo!!!  ","email":"user6@example.com"}
    Then the system should normalize the city input or reject it based on OpenWeatherMap recognition
    And if OpenWeatherMap recognizes the normalized city then:
      | expected_status |
      | 201            |
    And a subscription record should be created in PostgreSQL with city equal to the normalized value and status "pending"
    And a confirmation email should be sent to "user6@example.com"
    And if OpenWeatherMap does not recognize the normalized city then:
      | expected_status |
      | 400            |
    And no subscription record should be created in PostgreSQL for email "user6@example.com"
    And no confirmation email should be sent to "user6@example.com"
```
