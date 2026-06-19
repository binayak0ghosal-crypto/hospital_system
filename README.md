# Secure Hospital Patient Dashboard

A relational, role-based backend management dashboard constructed using Python 3 and SQLite. The application features explicit schema security structures alongside data integrity constraints to control infrastructure access and prevent resource multi-booking conflicts.

## Security Architectures
* **Cryptographic Salting & Hashing:** Avoids plaintext exposures by converting user account records natively via an individual randomized cryptographic salt concatenated against `SHA-256` digest definitions.
* **Role-Based Access Control (RBAC):** Restricts business logic visibility scopes depending on authenticated identities:
  * **Admins:** Global audit capabilities, credential management, system metrics logs.
  * **Doctors:** Filtered views tracking only assigned patient appointment blocks and historical health indicators.
  * **Patients:** Sandboxed views preventing read access outside of individual appointment entries.

---

## Database Schema Layout

| Users Table (RBAC Core) | Doctors Table | Patients Table | Appointments Table |
| :--- | :--- | :--- | :--- |
| `user_id` **(PK)** | `doctor_id` **(PK)** | `patient_id` **(PK)** | `appointment_id` **(PK)** |
| `username` *(Unique)* | `user_id` **(FK ➔ Users)** | `user_id` **(FK ➔ Users)** | `doctor_id` **(FK ➔ Doctors)** |
| `password_hash` | `name` | `name` | `patient_id` **(FK ➔ Patients)** |
| `salt` | `specialty` | `dob` | `appointment_date` |
| `role` *(Admin/Doctor/Patient)*| | `medical_history` | `appointment_time` |

### Double-Booking Prevention Rule
The scheduling process utilizes a multi-column database structural constraint explicitly defined on the **Appointments** table:
```sql
UNIQUE(doctor_id, appointment_date, appointment_time)
