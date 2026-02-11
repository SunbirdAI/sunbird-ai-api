import Header from '../components/Header';
import Footer from '../components/Footer';

export default function PrivacyPolicy() {
  return (
    <div className="min-h-screen bg-white dark:bg-black flex flex-col">
      <Header />
      
      <main className="flex-1 pt-24 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-8">Privacy Policy</h1>
          
          <div className="space-y-8 text-gray-700 dark:text-gray-300">
            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Introduction</h2>
              <p className="leading-relaxed">
                Welcome to the Privacy Policy of Sunbird AI. We understand that
                privacy online is important to users of our services, especially when
                utilizing our WhatsApp translation bot. This statement governs our
                privacy policies with respect to the collection, use, and disclosure
                of personal information when using our services.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Personally Identifiable Information</h2>
              <p className="leading-relaxed">
                Personally Identifiable Information refers to any information that
                identifies or can be used to identify, contact, or locate the person
                to whom such information pertains, including, but not limited to,
                name, address, phone number, email address, IP address, location, and
                browser.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">
                What Personally Identifiable Information is collected?
              </h2>
              <p className="leading-relaxed">
                We may collect basic user profile information from all users of our
                services. Additional information may be collected from users of our
                WhatsApp translation bot, including but not limited to, the content of
                messages for translation purposes.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">
                How is Personally Identifiable Information stored?
              </h2>
              <p className="leading-relaxed">
                Personally Identifiable Information collected by Sunbird AI is
                securely stored and is not accessible to third parties or employees of
                Sunbird AI except for use as indicated above.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">
                What choices are available to users regarding collection, use, and
                distribution of the information?
              </h2>
              <p className="leading-relaxed">
                Users may opt-out of certain data collection practices as outlined in
                this Privacy Policy by contacting Sunbird AI.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Changes to this Privacy Policy</h2>
              <p className="leading-relaxed">
                Sunbird AI reserves the right to update or change our Privacy Policy
                at any time. Users will be notified of any changes by posting the new
                Privacy Policy on this page.
              </p>
            </div>

            <div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">Contact Us</h2>
              <p className="leading-relaxed">
                If you have any questions about this Privacy Policy, please contact us
                at <a href="mailto:info@sunbird.ai" className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 underline">info@sunbird.ai</a>
              </p>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
