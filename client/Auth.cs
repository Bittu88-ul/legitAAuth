using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Security.Cryptography;
using Microsoft.Win32;
using System.IO;

namespace Auth
{
    public class Response
    {
        public bool success { get; set; }
        public string message { get; set; }
    }

    public class UserData
    {
        public string username { get; set; }
        public string expires_at { get; set; }
    }

    class AuthResponse
    {
        public bool success { get; set; }
        public string message { get; set; }
        public string detail { get; set; }
        public string dev_message { get; set; }
        public string version { get; set; }
        public UserData user { get; set; }
    }

    public static class LegitAuthApp
    {
        public static string name { get; set; }
        public static string ownerid { get; set; }
        public static string secret { get; set; }
        public static string version { get; set; }
        
        public static Response response = new Response();
        public static UserData user_data = new UserData();
        public static string dev_message { get; set; }
        public static string server_version { get; set; }
        
        private static bool initialized = false;
        private static readonly HttpClient client = new HttpClient();
        private static string _apiUrl = "https://legitauth1-3.onrender.com/api/client";

        public static void init(string _name, string _ownerid, string _secret, string _version)
        {
            name = _name;
            ownerid = _ownerid;
            secret = _secret;
            version = _version;
            initialized = true;
            response.success = true;
            response.message = "Initialized Successfully";
        }

        private static string GetHWID()
        {
            try
            {
                string hwid = "";
                // Use built-in Windows Registry instead of System.Management to avoid manual reference setup
                using (RegistryKey key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Cryptography"))
                {
                    if (key != null)
                    {
                        object val = key.GetValue("MachineGuid");
                        if (val != null)
                        {
                            hwid = val.ToString();
                        }
                    }
                }
                
                // Fallback to Environment variables if Registry fails
                if (string.IsNullOrEmpty(hwid))
                {
                    hwid = Environment.MachineName + Environment.UserName;
                }

                using (SHA256 sha256 = SHA256.Create())
                {
                    byte[] bytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(hwid));
                    StringBuilder builder = new StringBuilder();
                    for (int i = 0; i < bytes.Length; i++)
                    {
                        builder.Append(bytes[i].ToString("x2"));
                    }
                    return builder.ToString();
                }
            }
            catch
            {
                return "UNKNOWN_HWID";
            }
        }

        // Auto Save/Load Credentials so the user doesn't have to manually create settings
        private static string CredentialFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "legitauth_creds.txt");

        public static void SaveCredentials(string username, string password)
        {
            try
            {
                File.WriteAllText(CredentialFile, $"{username}\n{password}");
            }
            catch { }
        }

        public static void LoadCredentials(out string username, out string password)
        {
            username = "";
            password = "";
            try
            {
                if (File.Exists(CredentialFile))
                {
                    string[] lines = File.ReadAllLines(CredentialFile);
                    if (lines.Length >= 2)
                    {
                        username = lines[0];
                        password = lines[1];
                    }
                }
            }
            catch { }
        }

        public static async Task login(string username, string password)
        {
            if (!initialized)
            {
                response.success = false;
                response.message = "Please initialize first";
                return;
            }

            var payload = new
            {
                owner_id = ownerid,
                secret = secret,
                app_name = name,
                username = username,
                password = password,
                hwid = GetHWID()
            };

            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");

            try
            {
                var apiResponse = await client.PostAsync($"{_apiUrl}/login", content);
                var responseString = await apiResponse.Content.ReadAsStringAsync();
                
                var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
                var authResult = JsonSerializer.Deserialize<AuthResponse>(responseString, options);

                if (apiResponse.IsSuccessStatusCode && authResult != null && authResult.success)
                {
                    user_data = authResult.user;
                    dev_message = authResult.dev_message;
                    server_version = authResult.version;
                    response.success = true;
                    response.message = "Login successful!";
                }
                else
                {
                    response.success = false;
                    if (authResult != null && !string.IsNullOrEmpty(authResult.detail))
                    {
                        if (authResult.detail.Contains("HWID Mismatch")) response.message = "HWID Mismatch";
                        else if (authResult.detail.Contains("Expired")) response.message = "Subscription expired";
                        else if (authResult.detail.Contains("Banned")) response.message = "Account banned";
                        else response.message = authResult.detail;
                    }
                    else
                    {
                        response.message = "Invalid credentials";
                    }
                }
            }
            catch (Exception)
            {
                response.success = false;
                response.message = "Connection error";
            }
        }

        public static async Task license(string key)
        {
            if (!initialized)
            {
                response.success = false;
                response.message = "Please initialize first";
                return;
            }

            var payload = new
            {
                owner_id = ownerid,
                secret = secret,
                app_name = name,
                license_key = key,
                hwid = GetHWID()
            };

            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");

            try
            {
                var apiResponse = await client.PostAsync($"{_apiUrl}/login", content);
                var responseString = await apiResponse.Content.ReadAsStringAsync();
                
                var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
                var authResult = JsonSerializer.Deserialize<AuthResponse>(responseString, options);

                if (apiResponse.IsSuccessStatusCode && authResult != null && authResult.success)
                {
                    user_data = authResult.user;
                    dev_message = authResult.dev_message;
                    server_version = authResult.version;
                    response.success = true;
                    response.message = "Key verified successfully!";
                }
                else
                {
                    response.success = false;
                    if (authResult != null && !string.IsNullOrEmpty(authResult.detail))
                    {
                        if (authResult.detail.Contains("HWID Mismatch")) response.message = "HWID Mismatch";
                        else if (authResult.detail.Contains("Expired")) response.message = "Key expired";
                        else if (authResult.detail.Contains("License key not found")) response.message = "Invalid key";
                        else response.message = authResult.detail;
                    }
                    else
                    {
                        response.message = "Invalid key";
                    }
                }
            }
            catch (Exception)
            {
                response.success = false;
                response.message = "Connection error";
            }
        }
    }
}
