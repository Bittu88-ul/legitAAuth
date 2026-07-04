using System;
using System.Threading.Tasks;

namespace LegitAuthExample
{
    class Program
    {
        private static LegitAuth.Auth authInstance;

        static async Task Main(string[] args)
        {
            Console.WriteLine("Initializing LegitAuth...");
            authInstance = new LegitAuth.Auth(
                name: "MyApp",
                ownerid: "YOUR_OWNER_ID",
                secret: "YOUR_SECRET",
                version: "1.0"
            );

            Console.Write("Username: ");
            string username = Console.ReadLine();
            
            Console.Write("Password: ");
            string password = Console.ReadLine();

            bool success = await authInstance.Login(username, password);

            if (success)
            {
                Console.WriteLine("Welcome to the premium application!");
                // Launch main app
            }
            else
            {
                Console.WriteLine("Access Denied.");
            }

            Console.ReadLine();
        }
    }
}
